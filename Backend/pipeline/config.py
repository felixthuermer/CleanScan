"""Run configuration passed from the SwiftUI app to the backend.

The app sends this as a single inline JSON string (``--config '{...}'``) or a
path to a JSON file (``--config-file``). Keeping it one dataclass keeps the
Swift/Python contract in one place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

# Target page sizes in millimetres (portrait). "match" is resolved at runtime
# from the document's own most-common page size.
PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),  # 8.5 x 11 in
}

MODE_AUTO = "auto"                # let the pipeline pick the lightest tool that works
MODE_RECONSTRUCT = "reconstruct"  # force layout-preserving reconstruction
MODE_FAITHFUL = "faithful"        # native-OCR overlay on the original scan
MODE_CLEAN = "clean"              # faithful overlay on a cleaned + straightened scan

ENGINE_WEASYPRINT = "weasyprint"
ENGINE_CHROMIUM = "chromium"

# Resize is an axis independent of the processing mode:
#   page_size  -> target size (a4 / letter / match)
#   resize_fit -> how pages are fit to it
RESIZE_FIT = "fit"      # fit each page into the full target box (letterbox, uniform w+h)
RESIZE_WIDTH = "width"  # normalize WIDTH only; height stays proportional (no aspect change)
RESIZE_NONE = "none"    # do not resize — keep each page's original size (may be mixed)


@dataclass
class RunConfig:
    # --- surfaced in the main window ---
    # Resize (independent of mode):
    page_size: str = "a4"            # "a4" | "letter" | "match"  (target size)
    resize_fit: str = RESIZE_FIT     # "fit" | "width"            (how to fit)
    # Processing mode:
    mode: str = MODE_AUTO            # "auto" | "reconstruct" | "faithful" | "clean"

    # --- Advanced (collapsed in the UI) ---
    # Clean mode straightens via deskew (rotation) — letter-safe. This optional
    # non-linear de-warp only helps genuinely curved/folded PHOTOS and can distort
    # letters on flat scans, so it is OFF by default.
    dewarp: bool = False
    # Reconstruction style: "positioned" rebuilds the ORIGINAL layout (crisp text
    # placed at its original coordinates + graphics kept in place); "flow" reflows
    # into a single column (MinerU/native).
    reconstruct_layout: str = "positioned"
    language: str = "de+en"          # OCR/parse languages, "+"-separated
    correction: bool = False         # optional Ollama German cleanup pass
    correction_model: str = "llama3.2:3B"
    engine: str = ENGINE_WEASYPRINT  # "weasyprint" | "chromium"
    quality_threshold: float = 0.60  # min mean OCR confidence to keep reconstruct

    # --- internal / advanced tuning ---
    dpi: int = 300                   # rasterization DPI for PDF pages (pre-OCR)
    ollama_host: str = "http://127.0.0.1:11434"

    def target_size_mm(self) -> tuple[float, float] | None:
        """Return (w, h) mm for a fixed target, or None for 'match'."""
        return PAGE_SIZES_MM.get(self.page_size)

    # -- language helpers ---------------------------------------------------
    def lang_codes(self) -> list[str]:
        """Normalized two-letter-ish codes, e.g. ['de', 'en']."""
        return [c.strip().lower() for c in self.language.replace("+", " ").split() if c.strip()]

    def tesseract_langs(self) -> str:
        """Tesseract traineddata names, e.g. 'deu+eng' (legacy fallback path)."""
        mapping = {"de": "deu", "en": "eng", "deu": "deu", "eng": "eng"}
        codes = [mapping.get(c, c) for c in self.lang_codes()] or ["eng"]
        return "+".join(dict.fromkeys(codes))  # dedupe, preserve order

    def vision_langs(self) -> str:
        """Apple Vision BCP-47 codes, e.g. 'de-DE,en-US' (primary OCR path)."""
        mapping = {
            "de": "de-DE", "en": "en-US", "fr": "fr-FR",
            "es": "es-ES", "it": "it-IT", "pt": "pt-BR", "nl": "nl-NL",
        }
        codes = [mapping.get(c, c) for c in self.lang_codes()] or ["en-US"]
        return ",".join(dict.fromkeys(codes))

    # -- (de)serialization --------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunConfig":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @classmethod
    def from_json(cls, text: str) -> "RunConfig":
        return cls.from_dict(json.loads(text) if text else {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
