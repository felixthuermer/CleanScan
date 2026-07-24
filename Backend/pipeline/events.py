"""JSON-lines event protocol between the Python backend and the SwiftUI app.

Every event is a single JSON object printed on its own line to stdout and
flushed immediately, so the front-end can update the queue UI live. Anything the
backend needs to say that is NOT a structured event (tracebacks, third-party
library chatter) must go to stderr so it never corrupts the stdout stream.

Event shapes
------------
status : progress within a stage
    {"event":"status","stage":"preprocessing","page":1,"pages":3,
     "progress":0.15,"detail":"deskew"}
log    : human-readable log line
    {"event":"log","level":"info","message":"..."}
done   : terminal success
    {"event":"done","output":"/abs/out.pdf","mode":"reconstruct","pages":3}
error  : terminal failure
    {"event":"error","message":"...","stage":"parsing"}

``stage`` is one of: preprocessing | parsing | rendering — matching the
ProcessingStatus enum on the Swift side. Finer-grained steps are reported via
the free-form ``detail`` field so the three-stage UI model stays simple.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

# The canonical stage names shared with the Swift ProcessingStatus enum.
STAGE_PREPROCESSING = "preprocessing"
STAGE_PARSING = "parsing"
STAGE_RENDERING = "rendering"


def _emit(obj: dict) -> None:
    """Write one compact JSON object as a line to stdout and flush."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def status(
    stage: str,
    *,
    progress: Optional[float] = None,
    page: Optional[int] = None,
    pages: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    """Report progress within a stage. ``progress`` is 0.0–1.0 overall."""
    obj: dict[str, Any] = {"event": "status", "stage": stage}
    if progress is not None:
        obj["progress"] = round(max(0.0, min(1.0, progress)), 4)
    if page is not None:
        obj["page"] = page
    if pages is not None:
        obj["pages"] = pages
    if detail is not None:
        obj["detail"] = detail
    _emit(obj)


def log(message: str, level: str = "info") -> None:
    """Emit a human-readable log line (info | warning | error)."""
    _emit({"event": "log", "level": level, "message": message})


def done(output: str, mode: str, *, tool: Optional[str] = None,
         pages: Optional[int] = None) -> None:
    """Terminal success event.

    ``mode`` is 'reconstruct' or 'faithful'; ``tool`` names the engine that
    produced it ('native' | 'mineru' | 'tesseract') so the UI can show whether
    the lightweight native path or heavy MinerU path was used.
    """
    obj: dict[str, Any] = {"event": "done", "output": output, "mode": mode}
    if tool is not None:
        obj["tool"] = tool
    if pages is not None:
        obj["pages"] = pages
    _emit(obj)


def error(message: str, *, stage: Optional[str] = None) -> None:
    """Terminal failure event."""
    obj: dict[str, Any] = {"event": "error", "message": message}
    if stage is not None:
        obj["stage"] = stage
    _emit(obj)
