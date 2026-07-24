"""Stage — page-size standardization.

Every output page ends up the same physical size (default A4). This happens at
render time, never by resizing the source scans pre-OCR.

Two routes:
* Reconstruct: content is reflowable HTML, so we simply fix the ``@page`` box —
  text reflows to the standardized width and every page is that size (see
  ``page_css``).
* Faithful: the OCR'd PDF still has the source pages' (possibly mixed) sizes, so
  we re-impose each page onto a fixed target box, scaled proportionally and
  centered, using PyMuPDF ``show_pdf_page`` which preserves the searchable text
  layer (see ``impose_pdf``).
"""

from __future__ import annotations

from collections import Counter

from .config import RunConfig, PAGE_SIZES_MM, RESIZE_WIDTH, RESIZE_NONE
from .preprocess import PreprocessResult

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
PT_PER_MM = PT_PER_INCH / MM_PER_INCH


def resolve_target_mm(cfg: RunConfig, pre: PreprocessResult) -> tuple[float, float]:
    """Resolve the target page size in mm (w, h), honouring 'match'."""
    fixed = PAGE_SIZES_MM.get(cfg.page_size)
    if fixed:
        return fixed

    # "match": most-common source page size (points -> mm), orientation preserved.
    if not pre.pages:
        return PAGE_SIZES_MM["a4"]
    sizes = [(round(p.width_pt), round(p.height_pt)) for p in pre.pages]
    (w_pt, h_pt), _ = Counter(sizes).most_common(1)[0]
    return (w_pt / PT_PER_MM, h_pt / PT_PER_MM)


def _target_wh_pt(cfg: RunConfig, pre: PreprocessResult) -> tuple[float, float]:
    """Target width/height in points, portrait for fixed sizes."""
    w_mm, h_mm = resolve_target_mm(cfg, pre)
    if cfg.page_size in PAGE_SIZES_MM and w_mm > h_mm:
        w_mm, h_mm = h_mm, w_mm
    return w_mm * PT_PER_MM, h_mm * PT_PER_MM


def content_box(cfg: RunConfig, pre: PreprocessResult,
                orig_w: float, orig_h: float, margin: float = 0.0
                ) -> tuple[float, float, float, float, float, float]:
    """Output page dimensions + the content placement box for one source page.

    Returns (page_w, page_h, box_x, box_y, box_w, box_h) in points.

    * ``fit``   — page is the fixed target box; content is scaled to fit and
                  centered (uniform width AND height across all pages).
    * ``width`` — page WIDTH is the target width; the height follows the source
                  aspect ratio, so nothing is stretched or letterboxed (uniform
                  width only; heights vary per page).
    """
    if cfg.resize_fit == RESIZE_NONE:
        # keep the page at its original size (no standardization)
        return orig_w, orig_h, margin, margin, orig_w - 2 * margin, orig_h - 2 * margin

    tw, th = _target_wh_pt(cfg, pre)
    if cfg.resize_fit == RESIZE_WIDTH:
        avail_w = tw - 2 * margin
        scale = avail_w / orig_w
        box_h = orig_h * scale
        return tw, box_h + 2 * margin, margin, margin, avail_w, box_h
    # fit
    avail_w, avail_h = tw - 2 * margin, th - 2 * margin
    scale = min(avail_w / orig_w, avail_h / orig_h)
    cw, ch = orig_w * scale, orig_h * scale
    return tw, th, (tw - cw) / 2.0, (th - ch) / 2.0, cw, ch


def page_css(cfg: RunConfig, pre: PreprocessResult) -> str:
    """@page rule for the reconstruct route (portrait target, sane margins)."""
    w_mm, h_mm = resolve_target_mm(cfg, pre)
    # Reconstructed text reflows vertically, so always use portrait for the fixed
    # target unless 'match' resolved to a landscape-dominant document.
    if cfg.page_size in PAGE_SIZES_MM and w_mm > h_mm:
        w_mm, h_mm = h_mm, w_mm
    return (
        f"@page {{ size: {w_mm:.2f}mm {h_mm:.2f}mm; margin: 18mm 16mm; }}"
    )


def impose_pdf(cfg: RunConfig, pre: PreprocessResult, src_pdf: str, out_pdf: str) -> int:
    """Re-lay every page of ``src_pdf`` onto the standardized size (fit or width).

    Preserves the text layer (searchable). Returns the page count.
    """
    import fitz  # PyMuPDF

    src = fitz.open(src_pdf)
    out = fitz.open()
    for page in src:
        r = page.rect
        pw, ph, x, y, cw, ch = content_box(cfg, pre, r.width, r.height, margin=0.0)
        newpage = out.new_page(width=pw, height=ph)
        newpage.show_pdf_page(fitz.Rect(x, y, x + cw, y + ch), src, page.number)
    n = out.page_count
    out.save(out_pdf, deflate=True, garbage=3)
    out.close()
    src.close()
    return n
