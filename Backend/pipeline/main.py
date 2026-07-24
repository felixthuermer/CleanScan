"""CLI entry point + orchestrator.

Usage:
    python -m pipeline.main --input FILE --output-dir DIR --config '{...json...}'
    python -m pipeline.main --input FILE --output-dir DIR --config-file cfg.json
    python -m pipeline.main --selfcheck

Emits JSON-lines progress on stdout (see ``events.py``); diagnostics go to
stderr. Exit code 0 on success, 1 on failure (an ``error`` event is emitted
first either way).

Routing (Auto mode): native Apple Vision OCR runs first (cheap, offline). If the
document is plain text it is reconstructed natively — MinerU is never loaded. Only
when tables/figures are detected (and MinerU is installed) does it escalate to the
heavy structural reconstruction. Low confidence, or detected structure without
MinerU, falls back to a faithful searchable overlay. Manual modes force a route.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback

from . import (events, preprocess, parse, quality, correct, standardize,
               render, fallback_ocr, vision_ocr, positioned, clean)
from .config import RunConfig, MODE_CLEAN
from .quality import ROUTE_NATIVE, ROUTE_MINERU, ROUTE_FAITHFUL, MIN_TEXT_CHARS_PER_PAGE


# --------------------------------------------------------------------------
# Self-check (used by setup.sh to verify the install)
# --------------------------------------------------------------------------
def _selfcheck() -> int:
    def _importable(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    report = {
        "python": sys.version.split()[0],
        "native_ocr": {
            "visionocr_helper": vision_ocr.is_available(),
            "path": vision_ocr.helper_path(),
        },
        "binaries": {
            "mineru": parse.is_available(),               # venv-aware detection
            "ocrmypdf": bool(shutil.which("ocrmypdf")),   # optional fallback
            "tesseract": bool(shutil.which("tesseract")),  # optional fallback
        },
        "modules": {
            m: _importable(m) for m in
            ("fitz", "PIL", "cv2", "numpy", "weasyprint", "pytesseract", "pillow_heif")
        },
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    # Minimum viable install: native OCR + PDF/render libs. MinerU/Tesseract optional.
    ok = (report["native_ocr"]["visionocr_helper"]
          and report["modules"]["fitz"] and report["modules"]["weasyprint"])
    return 0 if ok else 1


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def _render_reconstruction(parse_result, cfg, pre, workdir, out_pdf) -> bool:
    """Correct (optional) + render a Block IR. True on success."""
    if cfg.correction:
        correct.correct_blocks(parse_result.blocks, cfg)
    render.render_reconstructed(parse_result, cfg, pre, workdir, out_pdf)
    return True


def process(input_path: str, output_dir: str, cfg: RunConfig) -> str:
    """Run the full pipeline for one document. Returns the output PDF path."""
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)
    os.makedirs(output_dir, exist_ok=True)

    workdir = tempfile.mkdtemp(prefix="docdig_")
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_pdf = os.path.join(output_dir, f"{stem}_clean.pdf")
    try:
        # 1) preprocess
        pre = preprocess.run(input_path, workdir, cfg.dpi)
        n = len(pre.pages)
        image_paths = [p.image_path for p in pre.pages]

        # CLEAN mode: flatten + straighten (dewarp) the pages, THEN OCR the cleaned
        # image so the text layer lines up, and overlay it (faithful-on-clean).
        if cfg.mode == MODE_CLEAN:
            clean.clean_pages(pre, cfg, workdir)
            vp = vision_ocr.run([p.image_path for p in pre.pages], cfg)
            if vp:
                faithful_pdf = vision_ocr.build_faithful_pdf(
                    pre, vp, os.path.join(workdir, "clean.pdf"))
                tool = "native"
            else:
                faithful_pdf = fallback_ocr.make_faithful_pdf(input_path, pre, workdir, cfg)
                tool = "tesseract"
            standardize.impose_pdf(cfg, pre, faithful_pdf, out_pdf)
            events.done(out_pdf, "clean", tool=tool, pages=n)
            return out_pdf

        # 2) native OCR first (cheap; None if the helper isn't built)
        vision_pages = vision_ocr.run(image_paths, cfg)
        mean_conf = vision_ocr.mean_confidence(vision_pages)
        if mean_conf is None:  # no native OCR -> legacy Tesseract probe
            mean_conf = fallback_ocr.ocr_confidence(image_paths, cfg.tesseract_langs())
        if mean_conf is not None:
            events.log(f"mean OCR confidence: {mean_conf:.2f}")

        # 3) route
        mineru_available = parse.is_available()
        route, reason = quality.decide_route(cfg, vision_pages, mean_conf, mineru_available, pre)
        events.log(f"route = {route} ({reason})")

        produced = False
        final_mode = "faithful"
        tool: str | None = None

        # 4·0) layout-preserving reconstruction (default) — rebuilds the ORIGINAL
        #      layout from Vision boxes: crisp positioned text + graphics kept in
        #      place. Native, no MinerU needed. Used for both reconstruct routes.
        if (route in (ROUTE_MINERU, ROUTE_NATIVE) and vision_pages
                and cfg.reconstruct_layout == "positioned"):
            try:
                positioned.render_positioned(pre, vision_pages, cfg, workdir, out_pdf)
                produced, final_mode, tool = True, "reconstruct", "positioned"
            except Exception as exc:  # noqa: BLE001
                events.log(f"positioned reconstruction failed ({exc}); trying flow", "warning")
                sys.stderr.write(traceback.format_exc())

        # 4a) MinerU flow reconstruction (opt-in via reconstruct_layout=flow, or fallback)
        if not produced and route == ROUTE_MINERU:
            enhanced_pdf = preprocess.images_to_pdf(
                image_paths, os.path.join(workdir, "enhanced.pdf"))
            parse_result = parse.run(enhanced_pdf, workdir, cfg)
            good = (parse_result.available
                    and parse_result.text_chars >= MIN_TEXT_CHARS_PER_PAGE * max(1, n))
            if good:
                try:
                    _render_reconstruction(parse_result, cfg, pre, workdir, out_pdf)
                    produced, final_mode, tool = True, "reconstruct", "mineru"
                except Exception as exc:  # noqa: BLE001
                    events.log(f"MinerU render failed ({exc}); downgrading", "warning")
                    sys.stderr.write(traceback.format_exc())
            if not produced:
                route = ROUTE_NATIVE if vision_pages else ROUTE_FAITHFUL
                events.log(f"MinerU insufficient — downgrading to {route}", "warning")

        # 4b) native (light) reconstruction
        if not produced and route == ROUTE_NATIVE and vision_pages:
            try:
                parse_result = vision_ocr.parse_result_from_vision(vision_pages)
                _render_reconstruction(parse_result, cfg, pre, workdir, out_pdf)
                produced, final_mode, tool = True, "reconstruct", "native"
            except Exception as exc:  # noqa: BLE001
                events.log(f"native render failed ({exc}); using faithful", "warning")
                sys.stderr.write(traceback.format_exc())

        # 4c) faithful overlay (native if available, else Tesseract/OCRmyPDF)
        if not produced:
            if vision_pages:
                faithful_pdf = vision_ocr.build_faithful_pdf(
                    pre, vision_pages, os.path.join(workdir, "faithful.pdf"))
                tool = "native"
            else:
                faithful_pdf = fallback_ocr.make_faithful_pdf(input_path, pre, workdir, cfg)
                tool = "tesseract"
            standardize.impose_pdf(cfg, pre, faithful_pdf, out_pdf)
            produced, final_mode = True, "faithful"

        events.done(out_pdf, final_mode, tool=tool, pages=n)
        return out_pdf
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------
# Argument handling
# --------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.main", description="DocDigitizer backend")
    ap.add_argument("--input", help="input PDF or image")
    ap.add_argument("--output-dir", help="directory for the output PDF")
    ap.add_argument("--config", default="", help="inline JSON run config")
    ap.add_argument("--config-file", default="", help="path to JSON run config")
    ap.add_argument("--selfcheck", action="store_true",
                    help="report dependency availability and exit")
    args = ap.parse_args(argv)

    if args.selfcheck:
        return _selfcheck()

    if not args.input or not args.output_dir:
        ap.error("--input and --output-dir are required")

    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as fh:
            cfg = RunConfig.from_json(fh.read())
    else:
        cfg = RunConfig.from_json(args.config)

    try:
        process(args.input, args.output_dir, cfg)
        return 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(traceback.format_exc())
        events.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
