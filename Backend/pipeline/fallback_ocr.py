"""Faithful-overlay fallback + Tesseract ground-truth probe.

Two independent, CPU-only jobs both built on Tesseract (deu+eng):

1. ``ocr_confidence`` — a fast per-word confidence probe used by the quality
   gate to decide whether reconstruction is trustworthy for this document.
2. ``make_faithful_pdf`` — produces a searchable PDF by laying a real OCR text
   layer over the *original* scan (via OCRmyPDF). This is the safety-net "mode":
   still selectable/searchable, but the page image is preserved faithfully rather
   than reconstructed. Page-size standardization is applied afterwards
   (``standardize.impose_pdf``), so this output still ends up uniform.

This path deliberately shares no state with MinerU so the app stays usable even
if MinerU's heavy install is incomplete.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

from . import events
from .config import RunConfig
from .preprocess import PreprocessResult, images_to_pdf


# --------------------------------------------------------------------------
# Quality probe
# --------------------------------------------------------------------------
def ocr_confidence(image_paths: list[str], tess_langs: str) -> Optional[float]:
    """Mean Tesseract word confidence (0.0–1.0) across pages, or None if unavailable."""
    try:
        import pytesseract
        from pytesseract import Output
        from PIL import Image
    except Exception:
        return None
    if not shutil.which("tesseract"):
        return None

    total_conf = 0.0
    total_words = 0
    for p in image_paths:
        try:
            data = pytesseract.image_to_data(
                Image.open(p), lang=tess_langs, output_type=Output.DICT
            )
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"tesseract probe error on {p}: {exc}\n")
            continue
        for conf in data.get("conf", []):
            try:
                c = float(conf)
            except (TypeError, ValueError):
                continue
            if c >= 0:
                total_conf += c
                total_words += 1
    if total_words == 0:
        return None
    return (total_conf / total_words) / 100.0


# --------------------------------------------------------------------------
# Faithful searchable PDF
# --------------------------------------------------------------------------
def _original_source_pdf(input_path: str, pre: PreprocessResult, workdir: str) -> str:
    """A PDF of the *original* pages (not the enhanced ones), for faithful mode."""
    if pre.is_pdf and pre.source_pdf:
        return pre.source_pdf  # already a faithful original

    # Image input: re-export the untouched original frames, then wrap to PDF.
    from PIL import Image
    from .preprocess import _register_heif

    _register_heif()
    orig_dir = os.path.join(workdir, "orig")
    os.makedirs(orig_dir, exist_ok=True)
    paths: list[str] = []
    with Image.open(input_path) as im:
        frames = getattr(im, "n_frames", 1)
        for f in range(frames):
            if frames > 1:
                im.seek(f)
            out = os.path.join(orig_dir, f"orig_{f + 1:04d}.png")
            im.convert("RGB").save(out, "PNG")
            paths.append(out)
    return images_to_pdf(paths, os.path.join(workdir, "faithful_source.pdf"))


def make_faithful_pdf(
    input_path: str, pre: PreprocessResult, workdir: str, cfg: RunConfig
) -> str:
    """Return path to a searchable PDF over the original scan (OCRmyPDF)."""
    if not shutil.which("ocrmypdf"):
        raise RuntimeError("ocrmypdf is not installed; cannot produce faithful output")

    events.status(events.STAGE_RENDERING, progress=0.1, detail="faithful OCR")
    src_pdf = _original_source_pdf(input_path, pre, workdir)
    out_pdf = os.path.join(workdir, "faithful_ocr.pdf")

    cmd = [
        "ocrmypdf",
        "-l", cfg.tesseract_langs(),
        "--force-ocr",              # scans have no reliable existing text layer
        "--output-type", "pdf",
        "--optimize", "1",
        "--rotate-pages",           # fix 90°/180° page rotation (keeps image faithful)
        src_pdf, out_pdf,
    ]
    events.log("ocrmypdf: " + " ".join(cmd))
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
    )
    if proc.returncode != 0 or not os.path.exists(out_pdf):
        sys.stderr.write((proc.stdout or "")[-2000:] + "\n")
        raise RuntimeError(f"ocrmypdf failed (exit {proc.returncode})")

    events.status(events.STAGE_RENDERING, progress=0.7, detail="faithful OCR done")
    return out_pdf
