"""The score of data-model.md section 6.3. Pure functions: no AWS, no environment, no clock.

The weights and the threshold are a first guess (tuned in week 6), so they are named constants
here and nowhere else. Every Match stores its scoreParts, so a score can always be explained.
Whole numbers only: boto3 refuses floats, and all rounding below is integer half-up.
"""

from __future__ import annotations

from dataclasses import dataclass

from vocab import CATEGORIES

WEIGHT_CATEGORY = 40
WEIGHT_COLORS = 30
WEIGHT_CLIP_CATEGORY = 15
WEIGHT_CLIP_COLOR = 15

TOP_N = 3  # the tagger stores the top 3; anything beyond that is ignored


@dataclass(frozen=True)
class Score:
    total: int
    parts: dict[str, int]
    why: list[str]


def _half_up(numerator: int, denominator: int) -> int:
    """numerator / denominator rounded to the nearest whole number, halves up (positive inputs)."""
    return (2 * numerator + denominator) // (2 * denominator)


def _colors(row: dict) -> list[str]:
    """Distinct string colors, in stored order."""
    seen: list[str] = []
    for value in row.get("colors") or []:
        if isinstance(value, str) and value and value not in seen:
            seen.append(value)
    return seen


def _clip_scores(item: dict, key: str) -> dict[str, int]:
    """value -> whole-percent CLIP score (0 to 100) from the item's top 3 of `categories` or `colors`.

    Defensive on purpose: a tagged item without usable clipTags just earns no CLIP points.
    """
    tags = item.get("clipTags")
    entries = tags.get(key) if isinstance(tags, dict) else None
    scores: dict[str, int] = {}
    if not isinstance(entries, list):
        return scores
    for entry in entries[:TOP_N]:
        if not isinstance(entry, dict):
            continue
        value, raw = entry.get("value"), entry.get("score")
        if not isinstance(value, str) or isinstance(raw, bool):
            continue
        try:
            score = int(raw)  # Decimal, int
        except (TypeError, ValueError, ArithmeticError):
            continue
        scores.setdefault(value, max(0, min(100, score)))
    return scores


def score_pair(report: dict, item: dict) -> Score | None:
    """Score one report against one item. None when the category differs or is unknown.

    The candidate queries only return same-category rows, but the check is repeated here so a
    wrong row can never score 40 for free.
    """
    category = report.get("category")
    if not isinstance(category, str) or category != item.get("category"):
        return None
    if category not in CATEGORIES:
        return None
    label, clip_phrase = CATEGORIES[category]

    parts = {"category": WEIGHT_CATEGORY, "colors": 0, "clipCategory": 0, "clipColor": 0}
    why = [f"Same category: {label}"]

    report_colors = _colors(report)
    item_colors = _colors(item)
    shared = [color for color in report_colors if color in item_colors]
    smaller = min(len(report_colors), len(item_colors))
    if shared and smaller:
        parts["colors"] = _half_up(WEIGHT_COLORS * len(shared), smaller)
        why.append("Shared color: " + ", ".join(shared))

    category_clip = _clip_scores(item, "categories").get(category, 0)
    parts["clipCategory"] = _half_up(category_clip * WEIGHT_CLIP_CATEGORY, 100)
    if parts["clipCategory"] > 0 and clip_phrase:
        why.append(f"The photo looks like {clip_phrase} ({category_clip}%)")

    color_clip = _clip_scores(item, "colors")
    best_color, best_score = None, 0
    for color in report_colors:
        if color_clip.get(color, 0) > best_score:
            best_color, best_score = color, color_clip[color]
    parts["clipColor"] = _half_up(best_score * WEIGHT_CLIP_COLOR, 100)
    if parts["clipColor"] > 0 and best_color:
        why.append(f"The photo looks {best_color} ({best_score}%)")

    return Score(total=sum(parts.values()), parts=parts, why=why)
