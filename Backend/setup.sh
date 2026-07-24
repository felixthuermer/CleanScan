#!/usr/bin/env bash
#
# CleanScan setup (Apple Silicon macOS).
#
#   ./setup.sh                 # light install: native OCR + reconstruction + faithful
#   ./setup.sh --with-mineru   # also install MinerU (heavy structural reconstruction)
#
# Primary OCR is Apple Vision (compiled to Backend/bin/visionocr) — offline, no
# model download, great with German. The heavy MinerU install is optional: Auto
# mode works without it (structured docs fall back to a faithful searchable
# overlay; plain text reconstructs natively). Runtime is fully offline.
#
set -euo pipefail
cd "$(dirname "$0")"
BACKEND_DIR="$(pwd)"
VENV="$BACKEND_DIR/.venv"
WITH_MINERU=0
for a in "$@"; do [ "$a" = "--with-mineru" ] && WITH_MINERU=1; done

log()  { printf "\033[1;34m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m[error]\033[0m %s\n" "$*" >&2; exit 1; }

# --------------------------------------------------------------------------
log "Compiling the native OCR helper (Apple Vision)…"
command -v swiftc >/dev/null 2>&1 || die "swiftc not found. Install Xcode Command Line Tools: xcode-select --install"
mkdir -p bin
swiftc -O native/visionocr.swift -o bin/visionocr || die "failed to compile visionocr"
./bin/visionocr --list-langs >/dev/null 2>&1 && log "visionocr OK" || warn "visionocr built but --list-langs failed"

# --------------------------------------------------------------------------
log "Checking Homebrew…"
command -v brew >/dev/null 2>&1 || die "Homebrew is required. Install from https://brew.sh"
BREW_PREFIX="$(brew --prefix)"

log "Installing core system libraries…"
# python@3.12 (MinerU/modern deps), Pango/Cairo/gdk-pixbuf/libffi (WeasyPrint).
brew install python@3.12 pango cairo gdk-pixbuf libffi || die "brew install failed"

log "Installing optional legacy-fallback tools (best effort)…"
# Only used if the native helper is ever unavailable; safe to skip on failure.
brew install tesseract tesseract-lang ghostscript >/dev/null 2>&1 \
  || warn "optional Tesseract/Ghostscript not installed (native OCR is primary, so this is fine)"

PY312="$BREW_PREFIX/opt/python@3.12/bin/python3.12"
[ -x "$PY312" ] || PY312="$(command -v python3.12 || true)"
[ -x "$PY312" ] || die "python3.12 not found after brew install"

# --------------------------------------------------------------------------
log "Creating virtual environment ($VENV)…"
"$PY312" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel

log "Installing core Python dependencies…"
export DYLD_FALLBACK_LIBRARY_PATH="$BREW_PREFIX/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
python -m pip install -r requirements.txt

if [ "$WITH_MINERU" -eq 1 ]; then
  log "Installing MinerU (heavy; several GB of models on first run)…"
  python -m pip install -r requirements-mineru.txt
  log "Pre-downloading MinerU models…"
  if command -v mineru-models-download >/dev/null 2>&1; then
    mineru-models-download || warn "mineru-models-download reported an issue"
  else
    python -m mineru.cli.models_download 2>/dev/null \
      || warn "could not pre-fetch MinerU models; they will download on first run"
  fi
else
  log "Skipping MinerU (light install). Re-run with --with-mineru to add it."
fi

log "Freezing a reproducible lock file (requirements.lock.txt)…"
python -m pip freeze > requirements.lock.txt

# --------------------------------------------------------------------------
log "Running self-check…"
python -m pipeline.main --selfcheck || \
  warn "self-check flagged missing pieces (see above)"

cat <<EOF

$(log "Setup complete.")

  Backend venv : $VENV
  Native OCR   : $BACKEND_DIR/bin/visionocr
  MinerU       : $( [ "$WITH_MINERU" -eq 1 ] && echo installed || echo "not installed (optional)" )

  Generate test documents:
    "$VENV/bin/python" make_test_docs.py

  Process a document (Auto picks the lightest tool that works):
    "$VENV/bin/python" -m pipeline.main \\
        --input testdata/german_clean_scan.pdf \\
        --output-dir out \\
        --config '{"page_size":"a4","mode":"auto"}'
EOF
