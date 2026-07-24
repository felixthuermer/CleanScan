"""Layout-preserving reconstruction ("digital twin").

Rebuilds the document so it looks natively digital *in the original layout*:
every recognized text line is placed as crisp, selectable text at its original
position (from the Apple Vision bounding boxes), and every non-text element —
logo, QR code, stamps, redaction boxes, table rules, figures — is carried over
as a clean cropped image at its original position/size.

The result is a white page (not the scan), real searchable text, and a layout
that matches the source — unlike flow reconstruction (which linearizes) or
faithful overlay (which keeps the scan image).

Everything is drawn with PyMuPDF at absolute coordinates, so positioning is
exact. Pages are standardized to the target size, scaling all coordinates
proportionally (fit + center).
"""

from __future__ import annotations

import os

from . import events
from .config import RunConfig
from .preprocess import PreprocessResult
from .standardize import content_box
from .vision_ocr import OCRPage


def _graphic_regions(image_path, ocr: OCRPage, cv2, np):
    """Bounding boxes (pixel coords) of non-text ink: logos, QR, redactions,
    table rules, figures — everything that isn't recognized text."""
    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return [], None, None
    h, w = gray.shape

    ink = (gray < 165).astype(np.uint8)
    # mask out recognized text (padded a little so glyph edges don't leak)
    text = np.zeros((h, w), np.uint8)
    pad = max(1, int(0.004 * max(h, w)))
    for l in ocr.lines:
        x0, x1 = int(l.x * w), int((l.x + l.w) * w)
        top = l.top_origin_top()
        y0, y1 = int(top * h), int((top + l.h) * h)
        cv2.rectangle(text, (max(0, x0 - pad), max(0, y0 - pad)),
                      (min(w, x1 + pad), min(h, y1 + pad)), 1, -1)

    nontext = cv2.bitwise_and(ink, 1 - text)
    # close gaps so a logo / QR / figure becomes one component
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    nontext = cv2.morphologyEx(nontext, cv2.MORPH_CLOSE, k)

    num, _, stats, _ = cv2.connectedComponentsWithStats(nontext, 8)
    min_area = 0.0004 * w * h
    min_dim = max(12, int(0.008 * min(w, h)))
    regions = []
    for i in range(1, num):
        x, y, ww, hh, area = stats[i]
        if area < min_area:
            continue
        if ww < min_dim and hh < min_dim:
            continue
        if ww >= 0.99 * w and hh >= 0.99 * h:  # whole page (background)
            continue
        # thin full-width line hugging the top/bottom edge = scan artifact
        if ((y <= 0.01 * h or y + hh >= 0.99 * h)
                and hh <= max(6, 0.006 * h) and ww >= 0.4 * w):
            continue
        regions.append((x, y, x + ww, y + hh))
    return regions, w, h


def render_positioned(pre: PreprocessResult, vision_pages: list[OCRPage],
                      cfg: RunConfig, workdir: str, out_pdf: str) -> int:
    """Render a layout-preserving, real-text PDF. Returns the page count."""
    import fitz
    import cv2
    import numpy as np

    margin = 12.0
    crops_dir = os.path.join(workdir, "crops")
    os.makedirs(crops_dir, exist_ok=True)

    out = fitz.open()
    n = len(pre.pages)
    for pinfo, ocr in zip(pre.pages, vision_pages):
        pw, ph, x0, y0, cw, ch = content_box(cfg, pre, pinfo.width_pt, pinfo.height_pt, margin)
        page = out.new_page(width=pw, height=ph)

        # 1) non-text graphics as positioned crops (drawn first, text goes on top)
        regions, pw, ph = _graphic_regions(pinfo.image_path, ocr, cv2, np)
        if regions and pw:
            color = cv2.imread(pinfo.image_path, cv2.IMREAD_COLOR)
            for (cx0, cy0, cx1, cy1) in regions:
                crop = color[cy0:cy1, cx0:cx1]
                if crop.size == 0:
                    continue
                tmp = os.path.join(crops_dir, f"p{pinfo.index}_{cx0}_{cy0}.png")
                cv2.imwrite(tmp, crop)
                rect = fitz.Rect(x0 + cx0 / pw * cw, y0 + cy0 / ph * ch,
                                 x0 + cx1 / pw * cw, y0 + cy1 / ph * ch)
                try:
                    page.insert_image(rect, filename=tmp)
                except Exception:
                    pass

        # 2) recognized text as crisp digital text at its original position
        for l in ocr.lines:
            text = l.text.strip()
            if not text:
                continue
            lx = x0 + l.x * cw
            ltop = y0 + l.top_origin_top() * ch
            lh = max(l.h * ch, 4.0)
            box_w = max(l.w * cw, 1.0)
            # Recover the font size from the box geometry: Vision boxes bound the
            # text tightly, so fitting to width reproduces the original size and
            # prevents overflow; cap by height so a tall box can't inflate it.
            unit = fitz.get_text_length(text, fontname="helv", fontsize=1.0)
            fs_w = box_w / unit if unit > 0 else lh
            fontsize = max(3.5, min(lh * 0.95, fs_w))
            baseline = ltop + lh * 0.80
            try:
                page.insert_text((lx, baseline), text, fontsize=fontsize,
                                 fontname="helv", color=(0, 0, 0))
            except Exception:
                # character outside the base font — retry char-by-char, skip bad
                try:
                    safe = "".join(c if ord(c) < 0x2500 else "·" for c in text)
                    page.insert_text((lx, baseline), safe, fontsize=fontsize,
                                     fontname="helv", color=(0, 0, 0))
                except Exception:
                    pass

        events.status(events.STAGE_RENDERING, page=pinfo.index + 1, pages=n,
                      progress=0.4 + 0.5 * (pinfo.index + 1) / max(1, n),
                      detail="positioned layout")

    out.save(out_pdf, deflate=True, garbage=3)
    out.close()
    events.log(f"positioned reconstruction: {n} page(s)")
    return n
