"""Row -> response shape, with explicit field allowlists (api/schemas/shared/*.json).

Never returned: finderId, ownerId, any email, photoKey, listedPk, listedCategory,
openCategory, taggedAt, tagError, scoreParts, notifiedAt. Items carry isMine instead of
the finder's ID. Reports never carry the owner's ID.
"""

from __future__ import annotations

from photos import photo_link

WALLET_ID = "wallet-id"


def _clip_tags(raw: dict) -> dict:
    return {
        "categories": [{"value": e["value"], "score": int(e["score"])} for e in raw.get("categories", [])[:3]],
        "colors": [{"value": e["value"], "score": int(e["score"])} for e in raw.get("colors", [])[:3]],
    }


def _base(row: dict, sub: str) -> dict:
    return {
        "itemId": row["itemId"],
        "title": row["title"],
        "category": row["category"],
        "colors": list(row["colors"]),
        "foundLocation": row["foundLocation"],
        "foundAt": row["foundAt"],
        "createdAt": row["createdAt"],
        "status": row["status"],
        "tagStatus": row["tagStatus"],
        "isMine": row.get("finderId") == sub,
    }


def _wants_photo(row: dict, sub: str, always: bool) -> bool:
    # A wallet-id photo can show a name, a face or card numbers: only the finder gets a link
    # in Browse and item detail. Matches inside GET /reports/{reportId} always have one.
    return always or row.get("finderId") == sub or row["category"] != WALLET_ID


def item_summary(row: dict, sub: str, *, always_photo: bool = False) -> dict:
    out = _base(row, sub)
    if _wants_photo(row, sub, always_photo):
        out["photo"] = photo_link(row["itemId"])
    return out


def item_detail(row: dict, sub: str) -> dict:
    out = _base(row, sub)
    if row.get("description"):
        out["description"] = row["description"]
    if row.get("returnedAt"):
        out["returnedAt"] = row["returnedAt"]
    if row.get("tagStatus") == "TAGGED" and isinstance(row.get("clipTags"), dict):
        out["clipTags"] = _clip_tags(row["clipTags"])
    if _wants_photo(row, sub, False):
        out["photo"] = photo_link(row["itemId"])
    return out


def new_item(row: dict) -> dict:
    """The item just created: no photo link yet, isMine always true."""
    out = _base(row, row["finderId"])
    if row.get("description"):
        out["description"] = row["description"]
    return out


def report(row: dict) -> dict:
    out = {
        "reportId": row["reportId"],
        "category": row["category"],
        "colors": list(row["colors"]),
        "description": row["description"],
        "status": row["status"],
        "createdAt": row["createdAt"],
    }
    for optional in ("lostLocation", "lostAt", "closedAt"):
        if row.get(optional):
            out[optional] = row[optional]
    return out


def match(match_row: dict, item_row: dict, sub: str) -> dict:
    return {
        "item": item_summary(item_row, sub, always_photo=True),
        "score": int(match_row["score"]),
        "why": [str(line) for line in match_row.get("why", [])][:4],
        "createdAt": match_row["createdAt"],
    }
