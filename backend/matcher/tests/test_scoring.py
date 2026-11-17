"""Section 6.3: the score, its worked examples and its edge cases. Pure functions, no AWS."""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import make_item, make_report
from scoring import score_pair


def test_example_one_scores_91():
    report = make_report(colors=["black"])
    item = make_item(colors=["black", "green"])
    result = score_pair(report, item)
    assert result.total == 91
    assert result.parts == {"category": 40, "colors": 30, "clipCategory": 12, "clipColor": 9}
    assert result.why == [
        "Same category: Water bottle or mug",
        "Shared color: black",
        "The photo looks like a water bottle or a mug (81%)",
        "The photo looks black (62%)",
    ]


def test_example_two_clip_covers_a_color_mixup():
    report = make_report(colors=["black"])
    item = make_item(colors=["gray"], clip_colors=[{"value": "black", "score": 55}])
    result = score_pair(report, item)
    assert result.parts == {"category": 40, "colors": 0, "clipCategory": 12, "clipColor": 8}
    assert result.total == 60


def test_example_three_is_below_threshold():
    report = make_report(colors=["red"])
    item = make_item(colors=["black", "green"])
    assert score_pair(report, item).total == 52


def test_color_part_uses_the_smaller_color_count():
    # 2 shared of min(3, 2) = 2 -> 30. 1 shared of min(3, 2) = 2 -> 15.
    item = make_item(colors=["black", "green"], clip_categories=[], clip_colors=[])
    assert score_pair(make_report(colors=["black", "green", "red"]), item).parts["colors"] == 30
    assert score_pair(make_report(colors=["black", "red", "blue"]), item).parts["colors"] == 15


def test_color_rounding_is_half_up_not_bankers():
    # 1 shared of min(3, 3) = 30/3 = 10 exactly; 2 of 3 = 20. Use 1 of 4-ish via weights: 30*1/4 = 7.5 -> 8.
    item = make_item(colors=["black", "green", "red", "blue"], clip_categories=[], clip_colors=[])
    # report has 4 colors, shares 1 -> 30*1/4 = 7.5 -> 8 (banker's rounding would give 8 too), so also check 22.5.
    report = make_report(colors=["black", "white", "gray", "pink"])
    assert score_pair(report, item).parts["colors"] == 8
    report = make_report(colors=["black", "green", "red", "pink"])  # shares 3 of 4 -> 22.5 -> 23 (banker's: 22)
    assert score_pair(report, item).parts["colors"] == 23


def test_clip_rounding_is_half_up():
    # 50 * 15 / 100 = 7.5 -> 8
    item = make_item(clip_categories=[{"value": "water-bottle", "score": 50}], clip_colors=[])
    assert score_pair(make_report(), item).parts["clipCategory"] == 8


def test_clip_score_outside_the_top_three_counts_zero():
    cats = [{"value": "keys", "score": 50}, {"value": "bag", "score": 20}, {"value": "phone", "score": 10},
            {"value": "water-bottle", "score": 9}]
    result = score_pair(make_report(), make_item(clip_categories=cats))
    assert result.parts["clipCategory"] == 0


def test_decimal_scores_from_dynamodb_are_handled():
    item = make_item(clip_categories=[{"value": "water-bottle", "score": Decimal("81")}],
                     clip_colors=[{"value": "black", "score": Decimal("62")}])
    assert score_pair(make_report(), item).total == 91


def test_best_clip_color_across_report_colors():
    report = make_report(colors=["black", "green"])
    item = make_item(clip_colors=[{"value": "black", "score": 62}, {"value": "green", "score": 21}])
    result = score_pair(report, item)
    assert result.parts["clipColor"] == 9
    assert result.why[-1] == "The photo looks black (62%)"


def test_other_category_scores_at_most_85():
    report = make_report(category="other", colors=["black"])
    item = make_item(category="other", colors=["black"], clip_categories=[{"value": "other", "score": 100}],
                     clip_colors=[{"value": "black", "score": 100}])
    result = score_pair(report, item)
    # An `other` pair never gets CLIP phrase text, and the tagger never scores `other` in practice.
    assert result.parts["category"] == 40
    assert not any(line.startswith("The photo looks like") for line in result.why)


def test_other_category_with_realistic_tags_caps_at_85():
    report = make_report(category="other", colors=["black"])
    item = make_item(category="other", colors=["black"], clip_categories=[{"value": "keys", "score": 40}],
                     clip_colors=[{"value": "black", "score": 100}])
    assert score_pair(report, item).total == 40 + 30 + 0 + 15


def test_different_category_is_never_a_candidate():
    assert score_pair(make_report(category="keys"), make_item(category="water-bottle")) is None


def test_unknown_category_is_not_scored():
    assert score_pair(make_report(category="spaceship"), make_item(category="spaceship")) is None


def test_untagged_item_without_clip_tags_still_scores_category_and_colors():
    item = make_item(tagged=False)
    result = score_pair(make_report(), item)
    assert result.parts == {"category": 40, "colors": 30, "clipCategory": 0, "clipColor": 0}


@pytest.mark.parametrize("bad", [None, "x", [], {"categories": "x"}, {"categories": [None, 5, {"value": 1}]},
                                 {"categories": [{"value": "water-bottle", "score": "high"}]},
                                 {"categories": [{"value": "water-bottle", "score": True}]}])
def test_malformed_clip_tags_never_raise(bad):
    item = make_item()
    item["clipTags"] = bad
    result = score_pair(make_report(), item)
    assert result.parts["clipCategory"] == 0


def test_clip_scores_are_clamped():
    item = make_item(clip_categories=[{"value": "water-bottle", "score": 900}], clip_colors=[])
    assert score_pair(make_report(), item).parts["clipCategory"] == 15
    item = make_item(clip_categories=[{"value": "water-bottle", "score": -5}], clip_colors=[])
    assert score_pair(make_report(), item).parts["clipCategory"] == 0


def test_duplicate_and_empty_colors_do_not_inflate_the_score():
    report = make_report(colors=["black", "black", ""])
    item = make_item(colors=["black"], clip_categories=[], clip_colors=[])
    assert score_pair(report, item).parts["colors"] == 30


def test_no_colors_gives_zero_not_a_division_error():
    report = make_report(colors=[])
    assert score_pair(report, make_item()).parts["colors"] == 0


def test_parts_add_up_and_are_whole_numbers():
    result = score_pair(make_report(), make_item())
    assert sum(result.parts.values()) == result.total <= 100
    assert all(type(v) is int for v in result.parts.values())
