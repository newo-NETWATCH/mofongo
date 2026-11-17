"""The shared vocabulary of data-model.md section 2, as far as matching needs it.

When a list in section 2 changes, change this file in the same commit (section 2.4).
Adding a value is safe. Never rename or remove one that is already stored.
"""

from __future__ import annotations

# value -> (label for the "why" lines, CLIP phrase). `other` has no CLIP phrase: CLIP never says
# "other", so a pair in `other` gets no CLIP points for category and can score at most 85.
CATEGORIES: dict[str, tuple[str, str | None]] = {
    "phone": ("Phone", "a smartphone"),
    "laptop-tablet": ("Laptop or tablet", "a laptop or a tablet computer"),
    "headphones": ("Headphones or earbuds", "headphones or wireless earbuds"),
    "charger-cable": ("Charger or cable", "a phone charger or a cable"),
    "wallet-id": ("Wallet or ID card", "a wallet or an ID card"),
    "keys": ("Keys", "a set of keys or a key fob"),
    "bag": ("Backpack or bag", "a backpack or a bag"),
    "water-bottle": ("Water bottle or mug", "a water bottle or a mug"),
    "clothing": ("Clothing", "a jacket, hoodie, hat or scarf"),
    "glasses": ("Glasses", "eyeglasses or sunglasses"),
    "jewelry-watch": ("Jewelry or watch", "a piece of jewelry or a wristwatch"),
    "books-notes": ("Books or notebooks", "a book or a notebook"),
    "calculator-supplies": ("Calculator or school supplies", "a calculator or school supplies"),
    "other": ("Other", None),
}

COLORS: frozenset[str] = frozenset(
    {
        "black", "white", "gray", "red", "orange", "yellow",
        "green", "blue", "purple", "pink", "brown", "multicolor",
    }
)

ITEM_STATUS_LISTED = "LISTED"
TAG_PENDING = "PENDING"
TAG_TAGGED = "TAGGED"
REPORT_STATUS_OPEN = "OPEN"
