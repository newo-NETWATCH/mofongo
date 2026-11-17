"""The shared vocabulary of data-model.md sections 2.1 and 2.2, as the tagger needs it.

This must stay in step with data-model.md and backend/matcher/vocab.py (section 2.4: change
the forms, the schemas, the tagger and the doc in one commit). `python worker/check_vocab.py`
compares this file with both and exits non-zero when they differ.

Adding a value is safe. Never rename or remove one that is already stored.
"""

from __future__ import annotations

# Section 2.1. value -> CLIP phrase. The prompt is "a photo of {phrase}".
# `other` is left out on purpose: CLIP never says "other" (section 2.4), so a pair in
# `other` gets no CLIP points for category. The tagger scores the 13 phrases below.
CATEGORY_PHRASES: dict[str, str] = {
    "phone": "a smartphone",
    "laptop-tablet": "a laptop or a tablet computer",
    "headphones": "headphones or wireless earbuds",
    "charger-cable": "a phone charger or a cable",
    "wallet-id": "a wallet or an ID card",
    "keys": "a set of keys or a key fob",
    "bag": "a backpack or a bag",
    "water-bottle": "a water bottle or a mug",
    "clothing": "a jacket, hoodie, hat or scarf",
    "glasses": "eyeglasses or sunglasses",
    "jewelry-watch": "a piece of jewelry or a wristwatch",
    "books-notes": "a book or a notebook",
    "calculator-supplies": "a calculator or school supplies",
}

# Every value in section 2.1, including `other`, for the consistency check only.
ALL_CATEGORY_VALUES: tuple[str, ...] = (*CATEGORY_PHRASES, "other")

# Section 2.2. value -> CLIP word. The prompt is "a photo of a {word} object".
COLOR_WORDS: dict[str, str] = {
    "black": "black",
    "white": "white",
    "gray": "gray",
    "red": "red",
    "orange": "orange",
    "yellow": "yellow",
    "green": "green",
    "blue": "blue",
    "purple": "purple",
    "pink": "pink",
    "brown": "brown",
    "multicolor": "multicolored",
}

CATEGORY_PROMPT = "a photo of {}"
COLOR_PROMPT = "a photo of a {} object"


def category_values() -> list[str]:
    return list(CATEGORY_PHRASES)


def category_prompts() -> list[str]:
    return [CATEGORY_PROMPT.format(p) for p in CATEGORY_PHRASES.values()]


def color_values() -> list[str]:
    return list(COLOR_WORDS)


def color_prompts() -> list[str]:
    return [COLOR_PROMPT.format(w) for w in COLOR_WORDS.values()]
