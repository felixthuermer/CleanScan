"""Stage 5 — rendering the reconstructed document to a real-text PDF.

Assembles the parsed blocks into a semantic HTML document, injects the
standardized ``@page`` CSS and a Unicode-safe font stack, and renders with
WeasyPrint (pure Python, produces genuine selectable text — not an image).

German guarantee: we set a font stack that always resolves to a face with full
Latin coverage (bundled ``Resources/fonts`` if present, else macOS system
faces), so ä/ö/ü/ß never fall back to tofu.

If ``cfg.engine == 'chromium'`` and Playwright is installed, we render via
headless Chromium instead — the flagged fallback for cases where WeasyPrint
layout fidelity proves insufficient.
"""

from __future__ import annotations

import glob
import html
import os

from . import events
from .config import RunConfig, ENGINE_CHROMIUM
from .parse import (
    ParseResult, Block,
    KIND_HEADING, KIND_PARAGRAPH, KIND_TABLE, KIND_FIGURE, KIND_EQUATION,
)
from .standardize import page_css
from .preprocess import PreprocessResult

_FONTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Resources", "fonts")
)
_FONT_STACK = "'DocDigitizer Sans', 'Helvetica Neue', Arial, 'DejaVu Sans', sans-serif"


def _font_face_css() -> str:
    """@font-face for a bundled Unicode font, if one is shipped."""
    faces = sorted(glob.glob(os.path.join(_FONTS_DIR, "*.ttf")) +
                   glob.glob(os.path.join(_FONTS_DIR, "*.otf")))
    if not faces:
        return ""  # rely on system faces (macOS Helvetica/Arial cover umlauts)
    return "\n".join(
        f"@font-face {{ font-family: 'DocDigitizer Sans'; "
        f"src: url('file://{f}'); }}" for f in faces[:1]
    )


def _base_css(cfg: RunConfig, pre: PreprocessResult) -> str:
    return f"""
{_font_face_css()}
{page_css(cfg, pre)}
html {{ font-family: {_FONT_STACK}; }}
body {{ font-size: 10.5pt; line-height: 1.4; color: #111; }}
h1 {{ font-size: 19pt; margin: 0 0 8pt; }}
h2 {{ font-size: 15pt; margin: 14pt 0 6pt; }}
h3 {{ font-size: 12.5pt; margin: 12pt 0 5pt; }}
h4, h5, h6 {{ font-size: 11pt; margin: 10pt 0 4pt; }}
p {{ margin: 0 0 6pt; text-align: justify; }}
figure {{ margin: 10pt 0; text-align: center; page-break-inside: avoid; }}
figure img {{ max-width: 100%; height: auto; }}
figcaption {{ font-size: 9pt; color: #555; margin-top: 3pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 8pt 0;
        font-size: 9.5pt; page-break-inside: avoid; }}
th, td {{ border: 0.5pt solid #999; padding: 3pt 5pt; text-align: left;
        vertical-align: top; }}
th {{ background: #f0f0f0; font-weight: 600; }}
.equation {{ font-style: italic; text-align: center; margin: 8pt 0; }}
""".strip()


def _block_html(b: Block) -> str:
    if b.kind == KIND_HEADING:
        lvl = min(max(b.level, 1), 6)
        return f"<h{lvl}>{html.escape(b.text)}</h{lvl}>"
    if b.kind == KIND_PARAGRAPH:
        return f"<p>{html.escape(b.text)}</p>"
    if b.kind == KIND_EQUATION:
        return f"<p class='equation'>{html.escape(b.text)}</p>"
    if b.kind == KIND_TABLE:
        body = b.html.strip()
        if not body:
            # MinerU couldn't give HTML — embed the table image so nothing is lost
            if b.image_path and os.path.exists(b.image_path):
                return f"<figure><img src='file://{b.image_path}'></figure>"
            return ""
        cap = f"<figcaption>{html.escape(b.caption)}</figcaption>" if b.caption else ""
        return f"<div class='table-wrap'>{body}{cap}</div>"
    if b.kind == KIND_FIGURE:
        if b.image_path and os.path.exists(b.image_path):
            cap = f"<figcaption>{html.escape(b.caption)}</figcaption>" if b.caption else ""
            return f"<figure><img src='file://{b.image_path}'>{cap}</figure>"
        return ""
    return ""


def build_html(parse_result: ParseResult, cfg: RunConfig, pre: PreprocessResult) -> str:
    body = "\n".join(h for b in parse_result.blocks if (h := _block_html(b)))
    return (
        "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'>"
        f"<style>{_base_css(cfg, pre)}</style></head><body>{body}</body></html>"
    )


def _render_weasyprint(html_str: str, out_pdf: str, base_url: str) -> None:
    from weasyprint import HTML  # heavy import, kept local
    HTML(string=html_str, base_url=base_url).write_pdf(out_pdf)


def _render_chromium(html_str: str, out_pdf: str, base_url: str) -> None:
    from playwright.sync_api import sync_playwright  # optional
    html_path = os.path.join(base_url, "_render.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html_str)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("file://" + html_path)
        page.pdf(path=out_pdf, prefer_css_page_size=True, print_background=True)
        browser.close()


def render_reconstructed(
    parse_result: ParseResult, cfg: RunConfig, pre: PreprocessResult,
    workdir: str, out_pdf: str,
) -> str:
    """Render the reconstructed HTML to ``out_pdf`` and return its path."""
    events.status(events.STAGE_RENDERING, progress=0.2, detail="assembling HTML")
    html_str = build_html(parse_result, cfg, pre)

    events.status(events.STAGE_RENDERING, progress=0.5, detail=f"render ({cfg.engine})")
    if cfg.engine == ENGINE_CHROMIUM:
        _render_chromium(html_str, out_pdf, workdir)
    else:
        _render_weasyprint(html_str, out_pdf, workdir)

    events.status(events.STAGE_RENDERING, progress=0.95, detail="written")
    return out_pdf
