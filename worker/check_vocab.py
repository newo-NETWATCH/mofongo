"""Check that the tagger's word lists match data-model.md (2.1, 2.2) and backend/matcher/vocab.py.

    python worker/check_vocab.py

Exits 1 and prints every difference. Run it before a commit that touches any list (section 2.4:
the forms, the schemas, the tagger and the doc change in one commit). Needs no AWS or torch.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import vocab as worker_vocab  # noqa: E402


def doc_table(text: str, heading: str) -> list[list[str]]:
    """Rows (cells without the backticks) of the first table under the given ### heading."""
    start = text.index(heading)
    rows = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith("### ") and rows:
            break
        if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows[1:]  # drop the header row


def main() -> int:
    problems: list[str] = []
    doc = (REPO / "docs" / "data-model.md").read_text(encoding="utf-8")

    doc_cats = {r[0]: r[2] for r in doc_table(doc, "### 2.1 Categories")}
    doc_cols = {r[0]: r[2] for r in doc_table(doc, "### 2.2 Colors")}

    mine_cats = dict(worker_vocab.CATEGORY_PHRASES)
    for value, phrase in doc_cats.items():
        if value == "other":
            continue
        if mine_cats.get(value) != phrase:
            problems.append(f"category {value}: doc says {phrase!r}, worker has {mine_cats.get(value)!r}")
    for value in mine_cats:
        if value not in doc_cats:
            problems.append(f"category {value}: in the worker, not in data-model.md")
    if set(worker_vocab.ALL_CATEGORY_VALUES) != set(doc_cats):
        problems.append("ALL_CATEGORY_VALUES differs from data-model.md 2.1")

    if worker_vocab.COLOR_WORDS != doc_cols:
        problems.append(f"colors differ: doc {doc_cols}, worker {worker_vocab.COLOR_WORDS}")

    try:
        matcher = _load_matcher()
        matcher_cats = {k: v[1] for k, v in matcher.CATEGORIES.items()}
        if matcher_cats != {**mine_cats, "other": None}:
            problems.append("backend/matcher/vocab.py categories differ from the worker's")
        if set(matcher.COLORS) != set(worker_vocab.COLOR_WORDS):
            problems.append("backend/matcher/vocab.py colors differ from the worker's")
    except FileNotFoundError:
        problems.append("backend/matcher/vocab.py not found")

    for p in problems:
        print("MISMATCH:", p)
    if not problems:
        print(f"ok: {len(mine_cats)} category phrases (+ other) and {len(worker_vocab.COLOR_WORDS)} colors match")
    return 1 if problems else 0


def _load_matcher():
    import importlib.util

    path = REPO / "backend" / "matcher" / "vocab.py"
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("matcher_vocab", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    sys.exit(main())
