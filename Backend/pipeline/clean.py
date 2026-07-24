"""Clean mode — cleaned + straightened faithful overlay.

The visible page stays the ORIGINAL scan, but cleaned:
* illumination / fold-shadow flattening (divide out the paper's lighting) — this
  removes the "geknicktes Papier" shadows and uneven lighting,
* (best-effort) geometric de-warping so curved text becomes straight.

De-warping is applied with a safety net: if the result looks implausible (lost
area, wildly different aspect) it is rejected and the cleaned-but-not-warped image
is kept, so Clean never produces worse output than plain faithful — important for
dense tables where aggressive warping could distort columns.

Deskew already happened in preprocessing; Clean adds flattening (always) and
de-warping (when ``cfg.dewarp``). OCR must run AFTER cleaning so the text layer
lines up with the (possibly de-warped) image.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

from . import events
from .config import RunConfig
from .preprocess import PreprocessResult, PT_PER_INCH


# Levels applied after illumination normalization (the "document" look, à la
# Scannable): a pixel brighter than WHITE_PT of its LOCAL paper is snapped to pure
# white (kills paper texture / noise); darker than BLACK_PT becomes solid black;
# a soft ramp between keeps text edges smooth (no jagged binary).
WHITE_PT = 0.82
BLACK_PT = 0.48


def _remove_border_frame(gray, cv2, np) -> None:
    """Whiten the dark scanner-bezel frame / edge lines, in place.

    Removes dark connected components that touch the image border and are either
    long-thin (edge strips) or a hollow frame — while preserving solid dark
    content like redaction boxes (which are inset and solidly filled)."""
    h, w = gray.shape
    dark = (gray < 175).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    for i in range(1, num):
        x, y, ww, hh, area = stats[i]
        touches = x <= 2 or y <= 2 or x + ww >= w - 2 or y + hh >= h - 2
        if not touches:
            continue
        long_thin = ((ww > 0.5 * w and hh < 0.10 * h)
                     or (hh > 0.5 * h and ww < 0.10 * w))
        hollow = (ww > 0.5 * w or hh > 0.5 * h) and area / (ww * hh + 1) < 0.45
        # small isolated speck hugging the edge (scanner tick marks / dust)
        speck = area < 0.0008 * w * h and max(ww, hh) < 0.12 * max(h, w)
        if long_thin or hollow or speck:
            gray[labels == i] = 255


def enhance_document(image_path: str) -> None:
    """Scannable-style cleanup: flatten lighting, snap paper to white, kill noise.

    Local illumination is removed by dividing the page by a downscaled large-close
    background (bridges big dark regions → no halos). A levels curve then maps the
    result so only pixels clearly darker than the local paper survive as ink; the
    rest becomes pure white. Finally the scanner bezel/edge frame is whitened.
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    scale = 1.0 / 6.0
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
    k = max(3, (min(sw, sh) // 3) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
    bg = cv2.GaussianBlur(bg, (0, 0), k / 2.0)
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    bg = np.maximum(bg.astype(np.float32), 1.0)

    ratio = gray.astype(np.float32) / bg                       # 1.0 ≈ local paper
    out = np.clip((ratio - BLACK_PT) / (WHITE_PT - BLACK_PT), 0.0, 1.0) * 255.0
    out = out.astype(np.uint8)

    # Sharpen AFTER the levels: the paper is already uniform white by now, so the
    # unsharp mask crisps glyph edges (softened by rasterizing / de-warp
    # resampling) without amplifying paper noise into speckle.
    blur = cv2.GaussianBlur(out, (0, 0), 0.8)
    out = cv2.addWeighted(out, 1.6, blur, -0.6, 0)

    _remove_border_frame(out, cv2, np)
    # backstop: whiten the outermost thin frame
    m = max(3, int(0.004 * min(h, w)))
    out[:m, :] = 255; out[-m:, :] = 255; out[:, :m] = 255; out[:, -m:] = 255
    cv2.imwrite(image_path, cv2.cvtColor(out, cv2.COLOR_GRAY2BGR))


def _dewarp_exe() -> str | None:
    cand = os.path.join(os.path.dirname(sys.executable), "page-dewarp")
    if os.path.exists(cand):
        return cand
    import shutil
    return shutil.which("page-dewarp")


def _valid_dewarp(orig_path: str, new_path: str) -> bool:
    """Reject implausible de-warps (lost content / distorted aspect)."""
    try:
        import cv2
    except Exception:
        return False
    a = cv2.imread(orig_path, cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(new_path, cv2.IMREAD_GRAYSCALE)
    if a is None or b is None:
        return False
    ah, aw = a.shape
    bh, bw = b.shape
    if bw < 200 or bh < 200:
        return False
    ar, br = aw / ah, bw / bh
    if not (0.7 < br / ar < 1.43):          # aspect changed too much
        return False
    if (bw * bh) < 0.45 * (aw * ah):        # lost too much area
        return False
    return True


def dewarp(image_path: str, workdir: str, page_idx: int) -> str | None:
    """Best-effort de-warp via the page-dewarp CLI. Returns a path or None."""
    exe = _dewarp_exe()
    if not exe:
        return None
    outdir = os.path.join(workdir, f"dewarp_{page_idx}")
    os.makedirs(outdir, exist_ok=True)
    cmd = [exe, "-nb", "1", "-x", "0", "-y", "0", "-o", outdir, image_path]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"page-dewarp error: {exc}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write((proc.stdout or "")[-1500:] + "\n")
        return None
    outs = (glob.glob(os.path.join(outdir, "*_thresh.png"))
            or glob.glob(os.path.join(outdir, "*.png")))
    if not outs:
        return None
    return outs[0] if _valid_dewarp(image_path, outs[0]) else None


def clean_pages(pre: PreprocessResult, cfg: RunConfig, workdir: str) -> None:
    """De-warp (best-effort, first) then document-enhance each page, in place."""
    n = len(pre.pages)
    for pinfo in pre.pages:
        events.status(events.STAGE_PREPROCESSING, page=pinfo.index + 1, pages=n,
                      detail="cleaning", progress=(pinfo.index + 1) / n)

        # 1) de-warp FIRST so the cleanup (below) works on the final geometry and
        #    handles any edges the de-warp introduces.
        if cfg.dewarp:
            warped = dewarp(pinfo.image_path, workdir, pinfo.index)
            if warped:
                import cv2
                img = cv2.imread(warped, cv2.IMREAD_GRAYSCALE)
                cv2.imwrite(pinfo.image_path, cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
                bh, bw = img.shape[:2]
                pinfo.px_width, pinfo.px_height = bw, bh
                pinfo.height_pt = pinfo.width_pt * (bh / bw)
                events.log(f"page {pinfo.index + 1}: de-warped")

        # 2) Scannable-style document enhancement (white paper, black text, no noise).
        enhance_document(pinfo.image_path)
    events.log("clean: document-enhanced" + (" (+ de-warp)" if cfg.dewarp else ""))
