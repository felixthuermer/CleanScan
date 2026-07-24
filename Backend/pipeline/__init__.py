"""DocDigitizer backend pipeline.

Turns a scanned PDF / image document into a clean, searchable PDF. The pipeline
runs fully offline at runtime and communicates progress to the SwiftUI front-end
as JSON-lines on stdout (see ``events.py``).

Stage order (see ``main.py``):
    preprocess -> parse (MinerU) -> quality gate -> [correct] -> standardize -> render
                                 \\-> fallback_ocr (faithful overlay) --------/
"""

__version__ = "0.1.0"
