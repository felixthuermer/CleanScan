"""Native macOS OCR (Apple Vision) via the ``visionocr`` Swift helper.

This is the primary, lightweight OCR path — it replaces Tesseract for the
confidence probe and the faithful-overlay text layer, and feeds the light
("native") reconstruction route. Vision runs on the Neural Engine, is fully
offline, needs no model download, and handles German ä/ö/ü/ß well.

The helper (Backend/bin/visionocr, built by setup.sh) is invoked per document
and returns JSON with per-line text, confidence and normalized bounding boxes.
If the helper is missing, ``run`` returns None and callers fall back to the
Tesseract path in ``fallback_ocr.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

from . import events
from .config import RunConfig
from .parse import Block, ParseResult, KIND_HEADING, KIND_PARAGRAPH
from .preprocess import PreprocessResult


@dataclass
class OCRLine:
    text: str
    confidence: float
    # normalized bbox, BOTTOM-LEFT origin (Vision convention)
    x: float
    y: float
    w: float
    h: float

    def top_origin_top(self) -> float:
        """Top edge as a fraction from the page top (0=top, 1=bottom)."""
        return 1.0 - (self.y + self.h)


@dataclass
class OCRPage:
    path: str
    width: int
    height: int
    mean_confidence: float
    lines: list[OCRLine] = field(default_factory=list)


# --------------------------------------------------------------------------
# Helper invocation
# --------------------------------------------------------------------------
def helper_path() -> Optional[str]:
    env = os.environ.get("DOCDIGITIZER_VISIONOCR")
    if env and os.path.exists(env):
        return env
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Backend/
    cand = os.path.join(backend, "bin", "visionocr")
    return cand if os.path.exists(cand) else None


def is_available() -> bool:
    return helper_path() is not None


def run(image_paths: list[str], cfg: RunConfig) -> Optional[list[OCRPage]]:
    """Run native OCR over the page images. None if the helper is unavailable."""
    helper = helper_path()
    if not helper:
        events.log("native OCR helper (visionocr) not found; will use fallback", "warning")
        return None

    events.status(events.STAGE_PARSING, progress=0.1, detail="native OCR (Vision)")
    cmd = [helper, "--langs", cfg.vision_langs(), *image_paths]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
        events.log("native OCR helper failed; will use fallback", "warning")
        return None

    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except ValueError as exc:
        sys.stderr.write(f"visionocr JSON parse error: {exc}\n")
        return None

    pages: list[OCRPage] = []
    for p in data.get("pages", []):
        lines = [
            OCRLine(text=l["text"], confidence=float(l["confidence"]),
                    x=float(l["x"]), y=float(l["y"]), w=float(l["w"]), h=float(l["h"]))
            for l in p.get("lines", [])
        ]
        pages.append(OCRPage(
            path=p.get("path", ""), width=int(p.get("width", 0)),
            height=int(p.get("height", 0)),
            mean_confidence=float(p.get("mean_confidence", 0.0)), lines=lines,
        ))
    total_lines = sum(len(pg.lines) for pg in pages)
    events.log(f"native OCR: {len(pages)} page(s), {total_lines} line(s)")
    return pages


def mean_confidence(pages: Optional[list[OCRPage]]) -> Optional[float]:
    """Line-weighted mean confidence across pages (0.0–1.0), or None."""
    if not pages:
        return None
    n = sum(len(p.lines) for p in pages)
    if n == 0:
        return None
    return sum(l.confidence for p in pages for l in p.lines) / n


# --------------------------------------------------------------------------
# Faithful overlay: original image + invisible searchable text layer
# --------------------------------------------------------------------------
def build_faithful_pdf(pre: PreprocessResult, pages: list[OCRPage], out_pdf: str) -> str:
    """Render each page image with an invisible, selectable Vision text layer."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    for pinfo, ocr in zip(pre.pages, pages):
        w_pt, h_pt = pinfo.width_pt, pinfo.height_pt
        page = doc.new_page(width=w_pt, height=h_pt)
        page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), filename=pinfo.image_path)
        for line in ocr.lines:
            if not line.text.strip():
                continue
            x0 = line.x * w_pt
            top = line.top_origin_top() * h_pt
            box_h = max(line.h * h_pt, 4.0)
            fontsize = max(4.0, box_h * 0.85)
            baseline = top + box_h * 0.85
            try:
                # render_mode=3 -> invisible text (searchable, not shown)
                page.insert_text((x0, baseline), line.text,
                                 fontsize=fontsize, fontname="helv", render_mode=3)
            except Exception:
                # a char outside the base font — skip that line rather than fail
                continue
    doc.save(out_pdf, deflate=True)
    doc.close()
    return out_pdf


# --------------------------------------------------------------------------
# Light reconstruction: group Vision lines into headings + paragraphs
# --------------------------------------------------------------------------
def blocks_from_vision(pages: list[OCRPage]) -> list[Block]:
    """Build a reflowable Block IR from plain-text pages (no tables/figures)."""
    blocks: list[Block] = []
    for pidx, page in enumerate(pages):
        items = [
            (line.top_origin_top(), line.x, line.h, line.text.strip())
            for line in page.lines if line.text.strip()
        ]
        if not items:
            continue
        items.sort(key=lambda t: (round(t[0], 3), t[1]))
        heights = sorted(h for _, _, h, _ in items)
        median_h = heights[len(heights) // 2] or 0.01

        para: list[tuple] = []
        prev_bottom: Optional[float] = None
        prev_h = median_h

        def flush() -> None:
            nonlocal para
            if not para:
                return
            text = " ".join(t for *_, t in para).strip()
            if text:
                blocks.append(Block(kind=KIND_PARAGRAPH, text=text, page=pidx))
            para = []

        for top, x, h, text in items:
            is_heading = h > 1.35 * median_h
            if is_heading:
                flush()
                blocks.append(Block(kind=KIND_HEADING, text=text, level=1, page=pidx))
                prev_bottom, prev_h = top + h, h
                continue
            if prev_bottom is not None and (top - prev_bottom) > 1.2 * prev_h:
                flush()  # paragraph break on a large vertical gap
            para.append((top, x, h, text))
            prev_bottom, prev_h = top + h, h
        flush()
    return blocks


def parse_result_from_vision(pages: list[OCRPage]) -> ParseResult:
    """Wrap native blocks as a ParseResult so render.py can consume them."""
    return ParseResult(blocks=blocks_from_vision(pages), available=True)
