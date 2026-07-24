"""Stage 1 — preprocessing.

Loads the input document (scanned PDF or image: JPEG/PNG/HEIC/TIFF), rasterizes
PDF pages, records each page's *original* dimensions (needed later for page-size
standardization) and applies light OpenCV enhancement (deskew / denoise /
contrast normalization).

Deliberate choice: we do NOT resize pages to the target page size here. Scaling
the source image before OCR degrades recognition — standardization happens later
at render time (see ``standardize.py``). Enhancement is contrast-only (LAB CLAHE
+ gentle denoise), never hard binarization, so embedded colour photos survive
for the figure-extraction step.

All heavy imports are lazy so ``--selfcheck`` and ``--help`` work with no deps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from . import events

# Image extensions we accept directly (PDFs handled separately).
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".webp"}
PT_PER_INCH = 72.0
# Rasterization cap: never render a page larger than this on its long side.
# ~2600px ≈ 220 DPI on A4 — plenty for OCR, and avoids upscaling scanned PDFs.
MAX_RASTER_LONG_PX = 2600
# Skip the (slow) NLM denoise above this pixel count; high-res scans don't need it.
DENOISE_MAX_PX = 1_600_000


@dataclass
class PageInfo:
    """One source page after preprocessing."""
    index: int                 # 0-based page order
    image_path: str            # enhanced page image (PNG) on disk
    width_pt: float            # original width in points (1/72 inch)
    height_pt: float           # original height in points
    px_width: int
    px_height: int
    dpi: float
    deskew_angle: float = 0.0  # degrees applied (0 if none)

    @property
    def orientation(self) -> str:
        return "landscape" if self.width_pt > self.height_pt else "portrait"


@dataclass
class PreprocessResult:
    pages: list[PageInfo] = field(default_factory=list)
    is_pdf: bool = False
    source_pdf: Optional[str] = None  # original PDF path (used by faithful mode)


def _register_heif() -> None:
    """Enable HEIC/HEIF loading in Pillow if pillow-heif is installed."""
    try:
        import pillow_heif  # type: ignore
        pillow_heif.register_heif_opener()
    except Exception:
        pass  # HEIC just won't load; other formats unaffected


def _estimate_skew(gray, cv2, np, max_angle: float = 7.0) -> float:
    """Estimate page skew (degrees) via projection-profile variance.

    Rotating the binarized page so text rows line up horizontally maximizes the
    variance of the row-sum profile (sharp peaks for text lines, valleys for
    gaps). Unlike a min-area bounding box this optimizes global text-line
    alignment, so it is robust to a single strong edge like a paper fold, a page
    border, or sparse text. Returns the angle to rotate the image to straighten
    it (0.0 if the skew is negligible).
    """
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = thr.shape
    scale = 1000.0 / max(h, w)
    if scale < 1.0:
        thr = cv2.resize(thr, (max(1, int(w * scale)), max(1, int(h * scale))),
                         interpolation=cv2.INTER_AREA)
    ch, cw = thr.shape[0] / 2.0, thr.shape[1] / 2.0

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D((cw, ch), angle, 1.0)
        rot = cv2.warpAffine(thr, m, (thr.shape[1], thr.shape[0]),
                             flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT,
                             borderValue=0)
        proj = rot.sum(axis=1, dtype=np.float64)
        # Cap the row sums so a single very dense row (a paper fold, an
        # underline, a table rule) can't dominate the objective — otherwise the
        # estimator locks onto that one line instead of the text baselines. The
        # 98th percentile flattens only extreme outliers, leaving text peaks
        # intact so clean pages stay accurate.
        cap = np.percentile(proj, 98)
        if cap > 0:
            proj = np.minimum(proj, cap)
        d = np.diff(proj)
        return float(np.dot(d, d))

    best_a, best_s = 0.0, -1.0
    for a in np.arange(-max_angle, max_angle + 0.01, 0.5):   # coarse
        s = score(float(a))
        if s > best_s:
            best_s, best_a = s, float(a)
    for a in np.arange(best_a - 0.5, best_a + 0.51, 0.1):    # fine
        s = score(float(a))
        if s > best_s:
            best_s, best_a = s, float(a)
    return 0.0 if abs(best_a) < 0.2 else round(best_a, 2)


def _enhance(image_path: str) -> float:
    """In-place deskew + denoise + CLAHE on a page image. Returns skew angle.

    Silently no-ops if OpenCV/NumPy are unavailable so the pipeline still runs.
    """
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return 0.0

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return 0.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- deskew: robust projection-profile estimate ---
    try:
        angle = _estimate_skew(gray, cv2, np)
    except Exception:
        angle = 0.0

    if angle != 0.0:
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        img = cv2.warpAffine(
            img, m, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )

    # --- gentle denoise (colour-preserving); skip on large scans (NLM is very
    #     slow there and high-DPI scans are already clean enough) ---
    try:
        if img.shape[0] * img.shape[1] <= DENOISE_MAX_PX:
            img = cv2.fastNlMeansDenoisingColored(img, None, 5, 5, 7, 21)
    except Exception:
        pass

    # --- contrast normalization on L channel only (keeps colour) ---
    try:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    except Exception:
        pass

    cv2.imwrite(image_path, img)
    return round(float(angle), 3)


def _load_pdf(path: str, pages_dir: str, dpi: int) -> list[PageInfo]:
    import fitz  # PyMuPDF

    infos: list[PageInfo] = []
    doc = fitz.open(path)
    n = doc.page_count
    for i in range(n):
        page = doc.load_page(i)
        rect = page.rect  # points
        # Cap the raster resolution. Scanned PDFs often set 1pt = 1px, so a naive
        # 300-DPI zoom upscales an already-high-res page ~4x (tens of megapixels)
        # — slow and no extra detail. Use the requested DPI but never let the long
        # side exceed MAX_LONG_PX.
        long_pt = max(rect.width, rect.height) or 1.0
        zoom = min(dpi / PT_PER_INCH, MAX_RASTER_LONG_PX / long_pt)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        out = os.path.join(pages_dir, f"page_{i + 1:04d}.png")
        pix.save(out)
        angle = _enhance(out)
        infos.append(PageInfo(
            index=i, image_path=out,
            width_pt=float(rect.width), height_pt=float(rect.height),
            px_width=pix.width, px_height=pix.height, dpi=float(zoom * PT_PER_INCH),
            deskew_angle=angle,
        ))
        events.status(events.STAGE_PREPROCESSING, page=i + 1, pages=n,
                      progress=(i + 1) / n * 0.9)
    doc.close()
    return infos


def _load_image(path: str, pages_dir: str) -> list[PageInfo]:
    from PIL import Image, ImageOps  # Pillow

    _register_heif()
    with Image.open(path) as im:
        frames = getattr(im, "n_frames", 1)  # multi-page TIFF support
        infos: list[PageInfo] = []
        for f in range(frames):
            if frames > 1:
                im.seek(f)
            # Apply EXIF orientation FIRST. Phones and many scanners store the
            # pixels sideways with an orientation flag; without honoring it the
            # page (and its OCR text layer) comes out rotated in the output.
            dpi_info = im.info.get("dpi")
            frame = ImageOps.exif_transpose(im).convert("RGB")
            dpi = float(dpi_info[0]) if dpi_info and dpi_info[0] else 200.0
            out = os.path.join(pages_dir, f"page_{f + 1:04d}.png")
            frame.save(out, "PNG")
            angle = _enhance(out)
            w_px, h_px = frame.size
            infos.append(PageInfo(
                index=f, image_path=out,
                width_pt=w_px * PT_PER_INCH / dpi,
                height_pt=h_px * PT_PER_INCH / dpi,
                px_width=w_px, px_height=h_px, dpi=dpi,
                deskew_angle=angle,
            ))
            events.status(events.STAGE_PREPROCESSING, page=f + 1, pages=frames,
                          progress=(f + 1) / frames * 0.9)
        return infos


def images_to_pdf(image_paths: list[str], out_pdf: str) -> str:
    """Wrap page images into a single PDF at their native pixel size (PyMuPDF)."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    for img in image_paths:
        imgdoc = fitz.open(img)
        pdf_bytes = imgdoc.convert_to_pdf()
        imgdoc.close()
        imgpdf = fitz.open("pdf", pdf_bytes)
        doc.insert_pdf(imgpdf)
        imgpdf.close()
    doc.save(out_pdf)
    doc.close()
    return out_pdf


def run(input_path: str, workdir: str, dpi: int = 300) -> PreprocessResult:
    """Preprocess ``input_path`` into ``workdir``; return page metadata."""
    pages_dir = os.path.join(workdir, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    ext = os.path.splitext(input_path)[1].lower()

    events.status(events.STAGE_PREPROCESSING, progress=0.02, detail="loading")
    if ext == ".pdf":
        infos = _load_pdf(input_path, pages_dir, dpi)
        result = PreprocessResult(pages=infos, is_pdf=True, source_pdf=input_path)
    elif ext in IMAGE_EXTS:
        infos = _load_image(input_path, pages_dir)
        result = PreprocessResult(pages=infos, is_pdf=False)
    else:
        raise ValueError(f"Unsupported input type: {ext or '(none)'}")

    events.status(events.STAGE_PREPROCESSING, progress=1.0,
                  detail=f"{len(result.pages)} page(s)")
    events.log(f"preprocessed {len(result.pages)} page(s) from {os.path.basename(input_path)}")
    return result
