"""Stage 2 — structure parsing with MinerU (primary, reconstruction route).

MinerU runs layout + OCR + table/figure detection and emits a Markdown file, a
``*_content_list.json`` describing every block in reading order, and cropped
figure/table images. We normalize that into a small intermediate
representation (``Block`` list) that ``correct.py`` and ``render.py`` consume.

Robustness notes
----------------
* MinerU's CLI flags and language codes shift between releases, so we invoke the
  ``mineru`` CLI (more stable than the Python API), and locate its outputs by
  globbing rather than assuming a fixed subdirectory.
* If MinerU is not installed, errors, or produces no usable text, ``run`` returns
  a result with ``available=False`` — ``main.py`` then routes to the faithful
  OCR fallback instead of shipping a broken reconstruction.
* German: MinerU's pipeline backend uses PaddleOCR, whose ``latin`` model covers
  ä/ö/ü/ß. We map German→``latin`` by default (override with ``MINERU_LANG``).
  German output is NOT trusted until the explicit umlaut check passes — the
  Tesseract ``deu`` fallback remains the ground truth.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

from . import events
from .config import RunConfig

# Block kinds in the intermediate representation.
KIND_HEADING = "heading"
KIND_PARAGRAPH = "paragraph"
KIND_TABLE = "table"
KIND_FIGURE = "figure"
KIND_EQUATION = "equation"


@dataclass
class Block:
    kind: str
    page: int = 0
    text: str = ""          # heading / paragraph / equation
    level: int = 0          # heading level (1..6)
    html: str = ""          # table body HTML
    image_path: str = ""    # absolute path for figure/table image
    caption: str = ""

    @property
    def is_text(self) -> bool:
        return self.kind in (KIND_HEADING, KIND_PARAGRAPH)


@dataclass
class ParseResult:
    blocks: list[Block] = field(default_factory=list)
    markdown: str = ""
    images_dir: str = ""
    available: bool = True     # False -> caller must use fallback OCR
    reason: str = ""           # why unavailable, if applicable

    @property
    def text_chars(self) -> int:
        return sum(len(b.text) for b in self.blocks if b.is_text)


def _mineru_lang(cfg: RunConfig) -> str:
    """MinerU pipeline ``-l`` language code, or "" to use the default recognizer.

    MinerU 3.x's ``-l`` only accepts specific scripts (ch, korean, arabic,
    cyrillic, devanagari, …) — there is NO 'latin'/'en'/'de'. Latin-script text
    (German/English) is handled by the default recognizer, so we pass no ``-l``.
    Advanced users can force a valid code via ``MINERU_LANG``.
    """
    return os.environ.get("MINERU_LANG", "")


def _mineru_cli() -> Optional[str]:
    """Resolve the MinerU CLI path.

    Prefer the venv bin next to the running interpreter — the backend runs as
    ``.venv/bin/python`` without "activating" the venv, so ``.venv/bin`` is not
    on PATH and a bare ``shutil.which('mineru')`` would miss it. Fall back to
    PATH for a system-wide install.
    """
    sibling = os.path.join(os.path.dirname(sys.executable), "mineru")
    if os.path.exists(sibling):
        return sibling
    return shutil.which("mineru")


def _is_available() -> bool:
    return _mineru_cli() is not None


def is_available() -> bool:
    """Public: is the MinerU CLI installed?"""
    return _is_available()


def _run_mineru_cli(input_path: str, out_dir: str, lang: str) -> bool:
    """Invoke the MinerU CLI. Returns True on success (exit 0)."""
    cli = _mineru_cli()
    if not cli:
        return False
    # MinerU 3.x has no --device flag; the device is chosen via env (it also
    # auto-detects MPS on Apple Silicon). Use the 'pipeline' backend so no VLM /
    # extra models are required.
    env = os.environ.copy()
    env.setdefault("MINERU_DEVICE_MODE", os.environ.get("MINERU_DEVICE", "mps"))
    base = [cli, "-p", input_path, "-o", out_dir, "-b", "pipeline"]
    attempts = ([base + ["-l", lang]] if lang else []) + [base]  # then default recognizer
    for i, cmd in enumerate(attempts):
        try:
            events.log(f"mineru attempt {i + 1}: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, check=False, env=env,
            )
            if proc.returncode == 0:
                return True
            # forward MinerU's own output to stderr for debugging
            sys.stderr.write((proc.stdout or "")[-3000:] + "\n")
        except FileNotFoundError:
            return False
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"mineru error: {exc}\n")
    return False


def _find_outputs(out_dir: str) -> tuple[Optional[str], Optional[str]]:
    """Return (content_list.json path, markdown path) found under out_dir."""
    cl = sorted(glob.glob(os.path.join(out_dir, "**", "*content_list.json"), recursive=True))
    md = sorted(glob.glob(os.path.join(out_dir, "**", "*.md"), recursive=True))
    return (cl[0] if cl else None, md[0] if md else None)


def _blocks_from_content_list(cl_path: str) -> list[Block]:
    base = os.path.dirname(cl_path)
    with open(cl_path, "r", encoding="utf-8") as fh:
        items = json.load(fh)

    def _abs(rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(base, rel))

    def _cap(item: dict) -> str:
        c = (item.get("table_caption") or item.get("image_caption")
             or item.get("chart_caption") or [])
        return " ".join(c) if isinstance(c, list) else str(c or "")

    blocks: list[Block] = []
    for item in items:
        page = int(item.get("page_idx", 0))
        itype = item.get("type", "text")
        if itype == "text":
            text = (item.get("text") or "").strip()
            if not text:
                continue
            level = int(item.get("text_level", 0) or 0)
            blocks.append(Block(
                kind=KIND_HEADING if level else KIND_PARAGRAPH,
                text=text, level=level or 0, page=page,
            ))
        elif itype == "table":
            blocks.append(Block(
                kind=KIND_TABLE, page=page,
                html=item.get("table_body", "") or "",
                image_path=_abs(item["img_path"]) if item.get("img_path") else "",
                caption=_cap(item),
            ))
        elif itype in ("image", "chart"):
            # MinerU 3.x emits 'chart' as a distinct type; both are figures.
            if item.get("img_path"):
                blocks.append(Block(
                    kind=KIND_FIGURE, page=page,
                    image_path=_abs(item["img_path"]), caption=_cap(item),
                ))
        elif itype == "equation":
            text = (item.get("text") or "").strip()
            if text:
                blocks.append(Block(kind=KIND_EQUATION, text=text, page=page))
        elif item.get("img_path"):
            # Unknown block type but it carries a cropped image — keep it as a
            # figure so content is never silently dropped as MinerU adds types.
            blocks.append(Block(
                kind=KIND_FIGURE, page=page,
                image_path=_abs(item["img_path"]), caption=_cap(item),
            ))
    return blocks


def run(input_path: str, workdir: str, cfg: RunConfig) -> ParseResult:
    """Parse ``input_path`` with MinerU into structured blocks."""
    if not _is_available():
        events.log("MinerU not installed — will use faithful OCR fallback", "warning")
        return ParseResult(available=False, reason="mineru-not-installed")

    out_dir = os.path.join(workdir, "mineru")
    os.makedirs(out_dir, exist_ok=True)
    lang = _mineru_lang(cfg)

    events.status(events.STAGE_PARSING, progress=0.1, detail=f"MinerU (lang={lang})")
    ok = _run_mineru_cli(input_path, out_dir, lang)
    if not ok:
        events.log("MinerU run failed — falling back to faithful OCR", "warning")
        return ParseResult(available=False, reason="mineru-failed")

    cl_path, md_path = _find_outputs(out_dir)
    if not cl_path:
        events.log("MinerU produced no content_list.json — falling back", "warning")
        return ParseResult(available=False, reason="mineru-no-output")

    blocks = _blocks_from_content_list(cl_path)
    markdown = ""
    if md_path and os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as fh:
            markdown = fh.read()

    events.status(events.STAGE_PARSING, progress=0.85,
                  detail=f"{len(blocks)} blocks")
    result = ParseResult(
        blocks=blocks, markdown=markdown,
        images_dir=os.path.dirname(cl_path), available=True,
    )
    events.log(f"MinerU parsed {len(blocks)} blocks, {result.text_chars} text chars")
    return result
