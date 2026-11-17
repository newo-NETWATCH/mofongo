"""Matcher behaviour from data-model.md section 6, driven through the Lambda handler under moto.

Covers: direction A (6.4), direction B (6.5), the score thresholds (6.3), the conditional-write
dedupe (6.7) with a publish counter, and the records and rows that must be skipped.
Events are realistic DynamoDB Streams records (DynamoDB-typed attribute values).
"""

from __future__ import annotations

import pytest

from conftest import TEST_ENV, make_item, make_report, new_id, stream_record

ITEMS = TEST_ENV["ITEMS_TABLE"]
REPORTS = TEST_ENV["REPORTS_TABLE"]


# ---- helpers --------------------------------------------------------------------------------

def run(*records):
    import app

    return app.handler({"Records": list(records)}, None)


def tagged_event(item, seq="1"):
    """What the Items stream delivers when the tagger saves its tags: PENDING -> TAGGED."""
    old = {**item, "tagStatus": "PENDING"}
    old.pop("clipTags", None)
    return stream_record(ITEMS, "MODIFY", new=item, old=old, seq=seq)


def report_event(report, seq="1"):
    """What the Reports stream delivers for a new report: an INSERT with no OldImage."""
    return stream_record(REPORTS, "INSERT", new=report, seq=seq)


def seed_item(aws, **kw):
    item = make_item(**kw)
    aws.items.put_item(Item=item)
    return item


def seed_report(aws, **kw):
    report = make_report(**kw)
    aws.reports.put_item(Item=report)
    return report


def rows(aws):
    return aws.matches.scan()["Items"]


@pytest.fixture
def publishes(aws):
    """Every SNS Publish call the matcher makes, as a list of kwargs. The real call still runs."""
    import clients

    client = clients.sns_client()
    calls: list[dict] = []
    real = client.publish

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    client.publish = spy
    return calls


# ---- direction A: an item gets its tags -----------------------------------------------------

def test_direction_a_tagged_item_matches_open_report(aws, publishes):
    owner = new_id()
    report = seed_report(aws, ownerId=owner, colors=["black"])
    item = seed_item(aws)

    assert run(tagged_event(item)) == {"batchItemFailures": []}

    [row] = rows(aws)
    assert (row["reportId"], row["itemId"]) == (report["reportId"], item["itemId"])
    assert row["score"] == 91
    assert dict(row["scoreParts"]) == {"category": 40, "colors": 30, "clipCategory": 12, "clipColor": 9}
    assert sum(row["scoreParts"].values()) == row["score"]
    assert 2 <= len(row["why"]) <= 4
    assert "notifiedAt" in row

    assert len(publishes) == 1
    call = publishes[0]
    assert call["TopicArn"] == TEST_ENV["ALERTS_TOPIC_ARN"]
    assert call["MessageAttributes"] == {"ownerId": {"DataType": "String", "StringValue": owner}}
    assert f"/reports/{report['reportId']}" in call["Message"]


def test_direction_a_delivers_only_to_the_owner_with_that_filter(aws):
    owner, other = new_id(), new_id()
    owner_queue, other_queue = aws.subscribe_owner(owner), aws.subscribe_owner(other)
    seed_report(aws, ownerId=owner, colors=["black"])
    run(tagged_event(seed_item(aws)))
    assert len(aws.messages(owner_queue)) == 1
    assert aws.messages(other_queue) == []


# ---- direction B: a report is filed ---------------------------------------------------------

def test_direction_b_new_report_matches_listed_item(aws, publishes):
    owner = new_id()
    item = seed_item(aws)
    report = seed_report(aws, ownerId=owner, colors=["black"])

    assert run(report_event(report)) == {"batchItemFailures": []}

    [row] = rows(aws)
    assert (row["reportId"], row["itemId"]) == (report["reportId"], item["itemId"])
    assert row["score"] == 91
    assert len(publishes) == 1
    assert publishes[0]["MessageAttributes"]["ownerId"]["StringValue"] == owner


def test_direction_b_ignores_untagged_items(aws, publishes):
    seed_item(aws, tagged=False)  # PENDING: direction A picks it up when the tags arrive
    report = seed_report(aws, colors=["black"])
    run(report_event(report))
    assert rows(aws) == [] and publishes == []


# ---- the score (6.3) through the whole path -------------------------------------------------

@pytest.mark.parametrize(
    ("report_colors", "item_colors", "clip_cats", "clip_cols", "expected", "matches"),
    [
        # all colors shared, no CLIP: 40 + 30 = 70
        (["black"], ["black", "green"], [], [], 70, True),
        # half of the smaller color count shared: 40 + 15 = 55, below 60
        (["black", "red"], ["black", "green"], [], [], 55, False),
        # no shared color, CLIP rescues it (worked example 2): 40 + 0 + 12 + 8 = 60, exactly the threshold
        (["black"], ["gray"], [{"value": "water-bottle", "score": 81}], [{"value": "black", "score": 55}], 60, True),
        # no shared color, red is not in the CLIP top 3 (worked example 3): 40 + 0 + 12 + 0 = 52
        (["red"], ["black", "green"], [{"value": "water-bottle", "score": 81}], [{"value": "black", "score": 62}], 52, False),
        # category alone is never enough
        (["red"], ["blue"], [], [], 40, False),
    ],
)
def test_score_thresholds(aws, publishes, report_colors, item_colors, clip_cats, clip_cols, expected, matches):
    report = seed_report(aws, colors=report_colors)
    item = seed_item(aws, colors=item_colors, clip_categories=clip_cats, clip_colors=clip_cols)

    run(tagged_event(item))

    if matches:
        [row] = rows(aws)
        assert row["score"] == expected
        assert len(publishes) == 1
    else:
        assert rows(aws) == [] and publishes == []
    # The score itself, whichever side of the threshold it falls on.
    from scoring import score_pair

    assert score_pair(report, item).total == expected


def test_threshold_comes_from_the_environment(aws, publishes, monkeypatch):
    import settings

    monkeypatch.setenv("MATCH_THRESHOLD", "95")
    settings.get_settings.cache_clear()
    seed_report(aws, colors=["black"])
    run(tagged_event(seed_item(aws)))  # scores 91
    assert rows(aws) == [] and publishes == []


# ---- categories differ ----------------------------------------------------------------------

def test_different_category_never_matches_in_either_direction(aws, publishes):
    report = seed_report(aws, category="keys", colors=["black"])
    item = seed_item(aws, category="water-bottle", colors=["black"])

    run(tagged_event(item))
    run(report_event(report))

    assert rows(aws) == [] and publishes == []


# ---- dedupe (6.7) ---------------------------------------------------------------------------

def test_second_run_of_the_same_pair_does_not_publish_again(aws, publishes):
    seed_report(aws, colors=["black"])
    item = seed_item(aws)
    event = tagged_event(item)

    run(event)
    [first] = rows(aws)
    assert len(publishes) == 1

    assert run(event) == {"batchItemFailures": []}  # at-least-once delivery: same record again
    assert len(publishes) == 1
    [second] = rows(aws)
    assert second == first  # not overwritten either (createdAt, notifiedAt unchanged)


def test_both_directions_finding_the_same_pair_send_one_email(aws, publishes):
    item = seed_item(aws)
    report = seed_report(aws, colors=["black"])

    run(report_event(report))
    run(tagged_event(item))

    assert len(rows(aws)) == 1
    assert len(publishes) == 1


def test_a_pair_recorded_earlier_is_not_republished(aws, publishes):
    report = seed_report(aws, colors=["black"])
    item = seed_item(aws)
    aws.matches.put_item(Item={"reportId": report["reportId"], "itemId": item["itemId"], "score": 91, "createdAt": "2026-10-20T18:00:00.000Z"})

    run(tagged_event(item))

    assert publishes == []
    assert "notifiedAt" not in rows(aws)[0]  # untouched: the existing row wins


# ---- skipped rows and records ---------------------------------------------------------------

def test_closed_reports_are_not_candidates_for_an_item(aws, publishes):
    seed_report(aws, colors=["black"], status="CLOSED")  # no openCategory, so not in the index
    run(tagged_event(seed_item(aws)))
    assert rows(aws) == [] and publishes == []


def test_returned_items_are_not_candidates_for_a_report(aws, publishes):
    seed_item(aws, status="RETURNED")  # no listedCategory, so not in the index
    report = seed_report(aws, colors=["black"])
    run(report_event(report))
    assert rows(aws) == [] and publishes == []


def test_item_record_that_is_not_listed_and_tagged_is_ignored(aws, publishes):
    seed_report(aws, colors=["black"])
    returned = make_item(status="RETURNED")
    pending_still = make_item(tagged=False)
    result = run(
        tagged_event(returned, seq="1"),
        stream_record(ITEMS, "MODIFY", new=pending_still, old=pending_still, seq="2"),  # PENDING -> PENDING
        stream_record(ITEMS, "INSERT", new=make_item(), seq="3"),  # a new item has no OldImage
    )
    assert result == {"batchItemFailures": []}
    assert rows(aws) == [] and publishes == []


def test_report_record_that_is_closed_or_not_new_is_ignored(aws, publishes):
    seed_item(aws)
    open_report = make_report(colors=["black"])
    closed = make_report(colors=["black"], status="CLOSED")
    result = run(
        report_event(closed, seq="1"),
        stream_record(REPORTS, "MODIFY", new=open_report, old=open_report, seq="2"),
        stream_record(REPORTS, "REMOVE", old=open_report, seq="3"),
    )
    assert result == {"batchItemFailures": []}
    assert rows(aws) == [] and publishes == []
