# DocDigitizer

Turn messy paper scans — phone photos or scanned PDFs — into clean, **searchable**
PDFs that look like they were born digital. Real selectable text, structured
tables, re-embedded figures, and one consistent page size per document.

**Everything runs locally and fully offline.** No cloud, no accounts, no uploads.
Built for Apple Silicon Macs.

<img src="Resources/icon.png" width="96" align="right" alt="DocDigitizer icon">

- 🧠 **Native OCR** (Apple Vision) — fast, on-device, great with German umlauts.
- 📄 **Layout-preserving reconstruction** — rebuilds the page as crisp digital text
  in the *original* layout.
- 🧻 **Scan cleanup** — flattens fold shadows, whitens paper, straightens skew.
- 🔒 **Offline & private** — your documents never leave your Mac.
- 🖥️ **Native SwiftUI app** with drag-and-drop, a live queue, and one-click backend
  setup (no terminal needed).

---

## How it works

A native **SwiftUI app** drives a local **Python pipeline**, one document at a time,
and streams progress back live.

```
 ┌────────────────┐   spawn per document    ┌───────────────────────────┐
 │  SwiftUI app   │ ───────────────────────▶ │  Python pipeline          │
 │  (queue, UI)   │                          │  preprocess → OCR → render │
 │                │ ◀─── JSON progress ───── │  (Apple Vision, PyMuPDF…)   │
 └────────────────┘                          └───────────────────────────┘
```

OCR is Apple **Vision** (native, offline). **MinerU** is an *optional* heavy add-on
only used for reflow reconstruction of complex tables.

---

## Requirements

- Apple Silicon Mac, macOS 13+ (Liquid-Glass UI on macOS 26+).
- [Homebrew](https://brew.sh) — the in-app setup uses it to install dependencies.
- Xcode **not** required to build (Command Line Tools are enough).

---

## Getting started

### 1. Build the app

```bash
cd App
./build-app.sh          # produces DocDigitizer.app (with icon, ad-hoc signed)
open DocDigitizer.app
```

> No Xcode needed — this builds with the command-line Swift toolchain. You can
> also `open App/Package.swift` in Xcode and press Run.

### 2. First launch — install the backend (no terminal!)

On first launch the app shows a **setup screen**. Click **Install backend** and
watch the progress; it provisions a local Python environment, the native OCR
helper, and the rendering tools. (Optionally tick *Install MinerU* for complex
table reflow — it's several GB and rarely needed.)

That's it. Drag scans onto the window and they process automatically.

<details>
<summary>Prefer the terminal? (optional)</summary>

```bash
cd Backend
./setup.sh                 # light install
./setup.sh --with-mineru   # also install MinerU (heavy, optional)
```
</details>

---

## Using it

- **Drag & drop** scans anywhere on the window, or click **Add Files…**
  (PDF, JPEG, PNG, HEIC, TIFF).
- Documents process **one at a time** through the live queue; open or reveal each
  finished PDF from its row.
- Pick your **output folder** at the bottom.

### Modes

Each mode has an **ⓘ** in the app explaining exactly what it does and its limits.

| Mode | What it does | Watch out for |
|------|--------------|---------------|
| **Auto** *(default)* | Reconstructs the original layout as digital text when OCR is confident; otherwise keeps a faithful scan overlay. | Decision depends on OCR confidence. |
| **Reconstruct** | Rebuilds the page as crisp, selectable digital text with logos/figures/redactions kept in place — looks born-digital. | Very dense multi-column pages can shift slightly; graphics are re-embedded as image crops. |
| **Faithful** | Keeps the exact scan image and adds an invisible searchable text layer. 100 % layout fidelity. | Still an image (not crisp digital text); no cleanup. |
| **Clean** | Faithful, but the scan is cleaned first: shadows removed, paper whitened, text straightened by deskew. | Image-based. Non-linear de-warp for curved photos is optional (Advanced), off by default (it can distort letters on flat scans). |

### Resize (independent of mode)

- **Fit** — every page becomes the same size (e.g. A4), content scaled to fit.
- **Width only** — same width, height stays proportional (no letterboxing).
- **Original size** — don't resize at all.
- **Size**: A4 · US Letter · Match the document's most common size.

---

## Building a distributable app (with icon, on your Mac)

The `build-app.sh` script already produces a proper `DocDigitizer.app` with the
app icon and an **ad-hoc code signature** — enough to run on **your own Mac**.

```bash
cd App && ./build-app.sh          # → App/DocDigitizer.app
```

- **Install it:** drag `DocDigitizer.app` into `/Applications`.
- **First open:** because it's ad-hoc signed, right-click the app → **Open** once
  to get past Gatekeeper (only needed the first time).
- **Change the icon:** replace `Resources/AppIcon.icns` with your own, then re-run
  `build-app.sh`. From an Xcode `.appiconset`:
  `iconutil -c icns -o Resources/AppIcon.icns path/to/AppIcon.iconset`
  (`Resources/make_icon.py` only generates a simple placeholder).

**Sharing with other people** requires an Apple Developer account: sign with a
*Developer ID Application* certificate and notarize the app. For personal use on
your own machine, the ad-hoc build above is all you need.

<details>
<summary>Regenerate the app icon</summary>

```bash
cd Resources
../Backend/.venv/bin/python make_icon.py   # writes AppIcon.icns
```
</details>

---

## Developer / CLI usage

Run the pipeline directly (after setup):

```bash
cd Backend
.venv/bin/python make_test_docs.py          # generate synthetic test docs
.venv/bin/python -m pipeline.main \
    --input testdata/german_clean_scan.pdf \
    --output-dir out \
    --config '{"mode":"auto","page_size":"a4"}'
```

Pipeline stages live in `Backend/pipeline/`: `preprocess` (deskew/denoise) →
`vision_ocr` (Apple Vision) → route → `positioned` (layout-preserving
reconstruction) / `clean` (scan cleanup) / `parse` (MinerU, optional) →
`standardize` → `render`. The Swift ↔ Python contract is JSON-lines
(`events.py`) plus `config.py`.

---

## Project layout

```
DocDigitizer/
  App/          SwiftUI app (Swift Package)   — build-app.sh → DocDigitizer.app
  Backend/      Python pipeline + setup.sh + make_test_docs.py
  Resources/    App icon + optional bundled font
```

---

## Troubleshooting

- **Setup fails / "Homebrew required":** install [Homebrew](https://brew.sh),
  then re-run setup from the app's gear menu.
- **App says "Backend not found":** open the gear menu → **Manage / reinstall
  backend**.
- **Complex tables come out as plain text (Reconstruct):** install MinerU via the
  setup screen's *Install MinerU* option.
- **First open blocked by Gatekeeper:** right-click the app → **Open**.

---

## Privacy

DocDigitizer processes everything on-device. After the one-time setup download,
you can turn Wi-Fi off and it keeps working — nothing is ever uploaded.

## License

Add your license of choice here before publishing (e.g. MIT).
