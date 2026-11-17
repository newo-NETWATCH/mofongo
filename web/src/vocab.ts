// Mirrors docs/data-model.md sections 2.1 and 2.2 and the enums in api/schemas. Keep in sync.

export const CATEGORIES = [
  { value: "phone", label: "Phone" },
  { value: "laptop-tablet", label: "Laptop or tablet" },
  { value: "headphones", label: "Headphones or earbuds" },
  { value: "charger-cable", label: "Charger or cable" },
  { value: "wallet-id", label: "Wallet or ID card" },
  { value: "keys", label: "Keys" },
  { value: "bag", label: "Backpack or bag" },
  { value: "water-bottle", label: "Water bottle or mug" },
  { value: "clothing", label: "Clothing" },
  { value: "glasses", label: "Glasses" },
  { value: "jewelry-watch", label: "Jewelry or watch" },
  { value: "books-notes", label: "Books or notebooks" },
  { value: "calculator-supplies", label: "Calculator or school supplies" },
  { value: "other", label: "Other" },
] as const;

export const COLORS = [
  { value: "black", label: "Black" },
  { value: "white", label: "White" },
  { value: "gray", label: "Gray" },
  { value: "red", label: "Red" },
  { value: "orange", label: "Orange" },
  { value: "yellow", label: "Yellow" },
  { value: "green", label: "Green" },
  { value: "blue", label: "Blue" },
  { value: "purple", label: "Purple" },
  { value: "pink", label: "Pink" },
  { value: "brown", label: "Brown" },
  { value: "multicolor", label: "Multicolor" },
] as const;

export type Category = (typeof CATEGORIES)[number]["value"];
export type Color = (typeof COLORS)[number]["value"];

/** Form hint from data-model 2.2. */
export const COLOR_HINT = "Silver is gray, gold is yellow, tan and beige are brown.";

/** The photo of a wallet-id item is hidden from non-finders (item.photo may be absent). */
export const PHOTO_HIDDEN_CATEGORY: Category = "wallet-id";

export const MAX_COLORS = 3;

const categoryLabels: Record<string, string> = Object.fromEntries(
  CATEGORIES.map((c) => [c.value, c.label]),
);
const colorLabels: Record<string, string> = Object.fromEntries(
  COLORS.map((c) => [c.value, c.label]),
);

export function categoryLabel(value: string): string {
  return categoryLabels[value] ?? value;
}

export function colorLabel(value: string): string {
  return colorLabels[value] ?? value;
}
