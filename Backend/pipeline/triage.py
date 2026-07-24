"""Automatic tool selection — does this document need structural reconstruction?

Auto mode uses only the cheap native OCR result (+ the page image) to decide
whether a document is plain enough for the lightweight native path, or whether
it has structure (tables / figures) that warrants MinerU. It deliberately biases
toward *preserving content*: when a table or figure is suspected it escalates,
so structure is never silently flattened. When the heuristic is wrong, the user
can override with the manual Reconstruct / Faithful modes.

Signals:
* tables  — rows made of several horizontally-separated text observations
            (Vision splits table cells into separate observations).
* figures — sizeable non-text regions of the page image with high local
            variance (a photo/chart, not blank paper).
"""

from __future__ import annotations

from typing import Optional

from .vision_ocr import OCRPage
from .preprocess import PreprocessResult


def _table_rows(page: OCRPage) -> int:
    """Count table-like rows: y-bands with >=3 observations spread across width."""
    lines = sorted(page.lines, key=lambda l: -l.y)  # top to bottom
    bands: list[dict] = []
    for l in lines:
        placed = False
        for band in bands:
            if abs(band["y"] - l.y) < max(0.012, l.h * 0.6):
                band["items"].append(l)
                placed = True
                break
        if not placed:
            bands.append({"y": l.y, "items": [l]})

    rows = 0
    for band in bands:
        items = band["items"]
        if len(items) >= 3:
            xs = sorted(i.x for i in items)
            if xs[-1] - xs[0] > 0.30:  # spread across the page, not one wrapped line
                rows += 1
    return rows


def _has_figure(image_path: str, page: OCRPage) -> bool:
    """Heuristic: a large non-text region of the page has real (non-blank) content."""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return False
    try:
        im = Image.open(image_path).convert("L")
    except Exception:
        return False

    W, H = im.size
    scale = 800.0 / max(W, H) if max(W, H) > 800 else 1.0
    im = im.resize((max(1, int(W * scale)), max(1, int(H * scale))))
    arr = np.asarray(im, dtype=np.float32)
    h, w = arr.shape

    # mask out text regions (Vision boxes are normalized, bottom-left origin)
    text = np.zeros((h, w), dtype=bool)
    for l in page.lines:
        x0, x1 = int(l.x * w), int((l.x + l.w) * w)
        top = l.top_origin_top()
        y0, y1 = int(top * h), int((top + l.h) * h)
        text[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True

    # grid of cells; flag non-text cells that are not blank paper
    cells = 16
    ch, cw = max(1, h // cells), max(1, w // cells)
    content_cells = 0
    total_nontext = 0
    for gy in range(0, h - ch + 1, ch):
        for gx in range(0, w - cw + 1, cw):
            block = text[gy:gy + ch, gx:gx + cw]
            if block.mean() > 0.15:      # mostly text -> skip
                continue
            total_nontext += 1
            patch = arr[gy:gy + ch, gx:gx + cw]
            if float(patch.std()) > 28.0:  # non-blank, non-text content
                content_cells += 1
    if total_nontext == 0:
        return False
    # a figure occupies a meaningful contiguous-ish fraction of the page
    return content_cells >= 6 and (content_cells / (cells * cells)) > 0.08


def needs_structure(pages: list[OCRPage], pre: PreprocessResult) -> tuple[bool, str]:
    """Return (needs_structure, reason) for Auto routing."""
    total_table_rows = sum(_table_rows(p) for p in pages)
    if total_table_rows >= 3:
        return True, f"{total_table_rows} table-like row(s)"

    for ocr, pinfo in zip(pages, pre.pages):
        if _has_figure(pinfo.image_path, ocr):
            return True, "embedded figure/graphic detected"

    return False, "plain text (no tables/figures detected)"
