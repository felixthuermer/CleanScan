#!/usr/bin/env python3
"""Generate synthetic test documents (and verify pipeline output).

Run with the backend venv's Python (needs pymupdf + pillow + numpy):

    .venv/bin/python make_test_docs.py            # generate into ./testdata
    .venv/bin/python make_test_docs.py --check out/german_clean_scan_clean.pdf

Generated docs exercise the acceptance criteria:
  * german_clean.pdf        — single A4 page, umlauts ä/ö/ü/ß + heading
  * mixed_sizes.pdf         — A4 portrait + Letter portrait + A4 landscape
  * table_and_image.pdf     — heading + real table + embedded figure
  * *_scan.pdf              — rasterized, slightly rotated + noisy, NO text layer
                              (forces the OCR path; the realistic input)

The ``--check`` mode extracts text with PyMuPDF and asserts: distinctive German
tokens survived, every page shares one size, and the text is really selectable.
"""

from __future__ import annotations

import argparse
import os
import sys

import fitz  # PyMuPDF

TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")

A4_P = (595.28, 841.89)
A4_L = (841.89, 595.28)
LETTER_P = (612.0, 792.0)

# Distinctive umlaut/ß tokens we assert on after processing.
GERMAN_TOKENS = ["Fußgängerüberführung", "Öffnungszeiten", "Größe", "Straße", "schöne Grüße"]

HEADING = "Prüfbericht zur Straßenüberführung"
BODY = (
    "Die Größe der Fußgängerüberführung wurde am Mädchenweg überprüft. "
    "Die Straße ist für schwere Fahrzeuge gesperrt. Änderungen an den "
    "Öffnungszeiten sind möglich. schöne Grüße gehen an alle Beteiligten. "
    "Das Ergebnis: die Brücke ist in Ordnung, außer an einer kleinen Stelle "
    "am äußeren Rand. Über weitere Maßnahmen wird noch entschieden."
)

TABLE_HEADERS = ["Straße", "Größe", "Prüfung"]
TABLE_ROWS = [
    ["Hauptstraße", "groß", "bestanden"],
    ["Nebenstraße", "mäßig", "zu prüfen"],
    ["Feldweg äußere", "klein", "ungeprüft"],
]


# --------------------------------------------------------------------------
# Drawing helpers (base-14 Helvetica covers Latin-1 incl. umlauts / ß)
# --------------------------------------------------------------------------
def _text(page, x, y, s, size=11, bold=False):
    page.insert_text((x, y), s, fontsize=size,
                     fontname="hebo" if bold else "helv", color=(0, 0, 0))


def _paragraph(page, rect, s, size=11):
    page.insert_textbox(rect, s, fontsize=size, fontname="helv",
                        color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT)


def _make_figure_png(path: str):
    """A simple synthetic 'photo/graphic' so figure extraction has something."""
    from PIL import Image, ImageDraw

    w, h = 480, 300
    img = Image.new("RGB", (w, h), (245, 245, 250))
    d = ImageDraw.Draw(img)
    bars = [(60, 210), (140, 150), (220, 90), (300, 170), (380, 60)]
    colors = [(60, 120, 200), (200, 80, 80), (90, 180, 110), (230, 170, 60), (140, 100, 200)]
    for (bx, top), c in zip(bars, colors):
        d.rectangle([bx, top, bx + 60, 260], fill=c)
    d.line([40, 260, 440, 260], fill=(40, 40, 40), width=2)
    d.text((150, 12), "Messwerte (Übersicht)", fill=(30, 30, 30))
    img.save(path, "PNG")


def _draw_table(page, x, y, col_w, row_h):
    rows = [TABLE_HEADERS] + TABLE_ROWS
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            cx = x + c * col_w
            cy = y + r * row_h
            page.draw_rect(fitz.Rect(cx, cy, cx + col_w, cy + row_h),
                           color=(0.4, 0.4, 0.4), width=0.6)
            _text(page, cx + 5, cy + row_h - 6, cell, size=10, bold=(r == 0))


# --------------------------------------------------------------------------
# Document builders
# --------------------------------------------------------------------------
def build_german_clean(path: str):
    doc = fitz.open()
    page = doc.new_page(width=A4_P[0], height=A4_P[1])
    _text(page, 60, 80, HEADING, size=18, bold=True)
    _paragraph(page, fitz.Rect(60, 110, 535, 400), BODY, size=12)
    _paragraph(page, fitz.Rect(60, 420, 535, 700),
               "Anhang: Diese Prüfung betrifft ausschließlich die genannte "
               "Straße. Für Rückfragen zu Öffnungszeiten wenden Sie sich an "
               "das zuständige Büro. Über die Größe der Maßnahme informieren "
               "wir gesondert.", size=12)
    doc.save(path)
    doc.close()


def build_mixed_sizes(path: str):
    doc = fitz.open()
    for i, (w, h, label) in enumerate([
        (*A4_P, "Seite 1 — A4 Hochformat"),
        (*LETTER_P, "Seite 2 — US Letter Hochformat"),
        (*A4_L, "Seite 3 — A4 Querformat"),
    ]):
        page = doc.new_page(width=w, height=h)
        _text(page, 55, 70, label, size=16, bold=True)
        _paragraph(page, fitz.Rect(55, 95, w - 55, h - 80),
                   f"{BODY} (Öffnungszeiten, Größe, Straße)", size=12)
    doc.save(path)
    doc.close()


def build_table_and_image(path: str):
    fig = os.path.join(TESTDATA, "_figure.png")
    _make_figure_png(fig)
    doc = fitz.open()
    page = doc.new_page(width=A4_P[0], height=A4_P[1])
    _text(page, 60, 75, "Bericht mit Tabelle und Abbildung", size=17, bold=True)
    _paragraph(page, fitz.Rect(60, 100, 535, 175),
               "Die folgende Tabelle zeigt Prüfergebnisse für mehrere Straßen. "
               "Die Abbildung darunter zeigt die zugehörigen Messwerte.", size=12)
    _draw_table(page, 60, 200, col_w=155, row_h=26)
    page.insert_image(fitz.Rect(60, 360, 380, 560), filename=fig)
    _text(page, 60, 585, "Abbildung 1: Übersicht der Messwerte.", size=9)
    doc.save(path)
    doc.close()
    os.remove(fig)


# --------------------------------------------------------------------------
# Scan simulation (rasterize + rotate + noise, strip text layer)
# --------------------------------------------------------------------------
def make_scan(src_pdf: str, out_pdf: str, dpi: int = 150, angle: float = 0.7):
    from PIL import Image
    import numpy as np

    src = fitz.open(src_pdf)
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = img.rotate(angle, expand=False, fillcolor=(255, 255, 255),
                         resample=Image.BICUBIC)
        arr = np.asarray(img).astype(np.int16)
        noise = np.random.normal(0, 6, arr.shape).astype(np.int16)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")

        tmp = out_pdf + f".p{page.number}.png"
        img.save(tmp, "PNG")
        imgpage = out.new_page(width=pix.width * 72.0 / dpi, height=pix.height * 72.0 / dpi)
        imgpage.insert_image(imgpage.rect, filename=tmp)
        os.remove(tmp)
    out.save(out_pdf)
    out.close()
    src.close()


# --------------------------------------------------------------------------
# Output verification (acceptance checks)
# --------------------------------------------------------------------------
def check_output(pdf_path: str) -> int:
    if not os.path.isfile(pdf_path):
        print(f"[check] file not found: {pdf_path}")
        return 1
    doc = fitz.open(pdf_path)
    full_text = "\n".join(doc.load_page(i).get_text() for i in range(doc.page_count))
    sizes = {(round(doc.load_page(i).rect.width), round(doc.load_page(i).rect.height))
             for i in range(doc.page_count)}
    n_images = sum(len(doc.load_page(i).get_images()) for i in range(doc.page_count))
    doc.close()

    found = [t for t in GERMAN_TOKENS if t in full_text]
    missing = [t for t in GERMAN_TOKENS if t not in full_text]
    uniform = len(sizes) == 1
    searchable = len(full_text.strip()) > 30

    print(f"[check] {os.path.basename(pdf_path)}")
    print(f"  page sizes      : {'uniform' if uniform else 'MIXED'} {sorted(sizes)}")
    print(f"  searchable text : {'yes' if searchable else 'NO'} ({len(full_text.strip())} chars)")
    print(f"  images embedded : {n_images}")
    print(f"  umlaut tokens   : found {found}")
    if missing:
        print(f"                    MISSING {missing}")
    ok = uniform and searchable and not missing
    print(f"  RESULT          : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------
def generate():
    os.makedirs(TESTDATA, exist_ok=True)
    build_german_clean(os.path.join(TESTDATA, "german_clean.pdf"))
    build_mixed_sizes(os.path.join(TESTDATA, "mixed_sizes.pdf"))
    build_table_and_image(os.path.join(TESTDATA, "table_and_image.pdf"))

    # Rasterized "scan" variants (the realistic inputs: no text layer).
    for name in ("german_clean", "mixed_sizes", "table_and_image"):
        make_scan(os.path.join(TESTDATA, f"{name}.pdf"),
                  os.path.join(TESTDATA, f"{name}_scan.pdf"))
    print(f"Wrote test documents to {TESTDATA}")
    for f in sorted(os.listdir(TESTDATA)):
        print("  ", f)


def main(argv):
    ap = argparse.ArgumentParser(description="Generate / verify DocDigitizer test docs")
    ap.add_argument("--check", metavar="PDF", help="verify a processed output PDF")
    args = ap.parse_args(argv)
    if args.check:
        return check_output(args.check)
    generate()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
