Optional: drop a full-Unicode TTF/OTF here (e.g. DejaVuSans.ttf or NotoSans-Regular.ttf).

If present, the renderer (Backend/pipeline/render.py) uses it via @font-face as
"CleanScan Sans", guaranteeing correct German ä/ö/ü/ß everywhere.

If this folder is empty, rendering falls back to macOS system faces (Helvetica /
Arial), which already cover German umlauts — so a bundled font is belt-and-
suspenders, not required.
