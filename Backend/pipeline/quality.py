"""Routing decision — which tool produces this document, and why.

Three routes, cheapest first:
* NATIVE   — light reconstruction from Apple Vision OCR (no MinerU load).
* MINERU   — heavy structural reconstruction (tables/figures/complex layout).
* FAITHFUL — keep the scan image, add a searchable text layer (safety net).

Auto picks NATIVE for plain text, escalates to MINERU only when structure is
detected (and MinerU is installed), and drops to FAITHFUL on low confidence or
when structure is present but MinerU is unavailable (so it is never flattened).
The choice is explicit — reported in the ``done`` event and shown in the UI.
"""

from __future__ import annotations

from typing import Optional

from . import triage
from .config import RunConfig, MODE_AUTO, MODE_FAITHFUL, MODE_RECONSTRUCT
from .vision_ocr import OCRPage
from .preprocess import PreprocessResult

ROUTE_NATIVE = "native"
ROUTE_MINERU = "mineru"
ROUTE_FAITHFUL = "faithful"

# Below this many recognized text chars per page, reconstruction likely lost the
# body text — used to reject a MinerU result post-parse (see main.py).
MIN_TEXT_CHARS_PER_PAGE = 20


def decide_route(
    cfg: RunConfig,
    vision_pages: Optional[list[OCRPage]],
    mean_conf: Optional[float],
    mineru_available: bool,
    pre: PreprocessResult,
) -> tuple[str, str]:
    """Return (route, reason)."""
    # --- explicit manual overrides ---
    if cfg.mode == MODE_FAITHFUL:
        return ROUTE_FAITHFUL, "user selected faithful overlay"
    if cfg.mode == MODE_RECONSTRUCT:
        if mineru_available:
            return ROUTE_MINERU, "user selected reconstruct (MinerU)"
        return ROUTE_NATIVE, "reconstruct requested but MinerU unavailable — native reconstruction"

    # --- MODE_AUTO ---
    if mean_conf is not None and mean_conf < cfg.quality_threshold:
        return ROUTE_FAITHFUL, f"low OCR confidence {mean_conf:.2f} (< {cfg.quality_threshold:.2f})"

    if not vision_pages:
        # native OCR unavailable — defer to MinerU if present, else faithful
        if mineru_available:
            return ROUTE_MINERU, "native OCR unavailable — using MinerU"
        return ROUTE_FAITHFUL, "native OCR unavailable — faithful overlay"

    # Positioned (layout-preserving) reconstruction handles tables/figures/
    # redactions natively, so there's no need to escalate to MinerU or drop to
    # faithful for structure — go straight to native positioned rendering.
    if cfg.reconstruct_layout == "positioned":
        return ROUTE_NATIVE, "layout-preserving reconstruction"

    needs, why = triage.needs_structure(vision_pages, pre)
    if needs:
        if mineru_available:
            return ROUTE_MINERU, f"structure detected: {why}"
        return ROUTE_FAITHFUL, f"structure detected ({why}) but MinerU unavailable — faithful preserves it"

    return ROUTE_NATIVE, f"native reconstruction — {why}"
