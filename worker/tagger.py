"""Zero-shot CLIP tagging (ADR 0004): open_clip ViT-B-32, laion2b_s34b_b79k weights.

The model loads ONCE, when Tagger() is built at service start. The text side (the 13 category
prompts and the 12 color prompts) is encoded once too, so each photo costs one image pass.

torch, open_clip and Pillow are imported inside the functions that need them, so the pure
parts (build_tags, top_k) import and test without them.

Scoring: softmax over the category prompts and, separately, over the color prompts, using the
model's own logit scale (about 100). Each list keeps its top 3 as {value, score}, with score a
whole percent from 0 to 100 (data-model.md section 4.1). Scores are not forced to add up to 100.
"""

from __future__ import annotations

import io
import logging
import math
from typing import Sequence

import vocab

log = logging.getLogger("tagger")

TOP_K = 3
# Pillow checks the real format from the bytes, not from the name or the Content-Type.
ALLOWED_FORMATS = ["JPEG", "PNG", "WEBP"]


class PhotoError(Exception):
    """The photo itself cannot be tagged and never will be (corrupt, too big, not an image).

    `reason` is a short fixed sentence. It is stored in Items.tagError, so it never holds
    exception text, file contents or anything the uploader controls.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def top_k(values: Sequence[str], probs: Sequence[float], k: int = TOP_K) -> list[dict]:
    """The k highest as [{value, score}], best first. Ties keep the order of the word list.

    score is a whole percent, rounded half up, clamped to 0..100.
    """
    if len(values) != len(probs):
        raise ValueError("values and probs differ in length")
    order = sorted(range(len(values)), key=lambda i: (-probs[i], i))[:k]
    return [{"value": values[i], "score": min(100, max(0, math.floor(probs[i] * 100 + 0.5)))} for i in order]


def build_tags(category_probs: Sequence[float], color_probs: Sequence[float]) -> dict:
    """The clipTags map of data-model.md section 4.1."""
    return {
        "categories": top_k(vocab.category_values(), category_probs),
        "colors": top_k(vocab.color_values(), color_probs),
    }


def load_image(data: bytes, max_pixels: int):
    """Decode photo bytes to an RGB Pillow image, or raise PhotoError.

    The pixel count is checked from the header before the pixels are decoded, so a small
    file that expands to a huge image (a decompression bomb) is refused cheaply.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS) as img:
            width, height = img.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise PhotoError("photo has too many pixels")
            img.load()
            img = ImageOps.exif_transpose(img)
            return img.convert("RGB")
    except PhotoError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        # Truncated or corrupt files raise OSError/SyntaxError/ValueError from the decoders.
        raise PhotoError("photo could not be read") from exc


class Tagger:
    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        weights_path: str | None = None,
        threads: int | None = None,
    ) -> None:
        import open_clip
        import torch

        if threads:
            torch.set_num_threads(threads)
        self._torch = torch
        # A local checkpoint path replaces the Hugging Face download (README, "Pinning the weights").
        source = weights_path or pretrained
        log.info("loading model %s (%s); the first start downloads the weights", model_name, "local file" if weights_path else pretrained)
        model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=source, device="cpu")
        model.eval()
        self._model = model
        self._preprocess = preprocess
        tokenizer = open_clip.get_tokenizer(model_name)
        with torch.inference_mode():
            self._category_text = self._encode_text(tokenizer, vocab.category_prompts())
            self._color_text = self._encode_text(tokenizer, vocab.color_prompts())
            self._scale = float(model.logit_scale.exp().item())
        log.info("model ready")

    def _encode_text(self, tokenizer, prompts: list[str]):
        features = self._model.encode_text(tokenizer(prompts))
        return features / features.norm(dim=-1, keepdim=True)

    def tag(self, image) -> dict:
        """Score one RGB Pillow image. Returns the clipTags map."""
        torch = self._torch
        with torch.inference_mode():
            pixels = self._preprocess(image).unsqueeze(0)
            features = self._model.encode_image(pixels)
            features = features / features.norm(dim=-1, keepdim=True)
            category_probs = (self._scale * features @ self._category_text.T).softmax(dim=-1)[0].tolist()
            color_probs = (self._scale * features @ self._color_text.T).softmax(dim=-1)[0].tolist()
        return build_tags(category_probs, color_probs)
