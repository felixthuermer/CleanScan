"""Optional post-OCR German correction pass (local Ollama).

Off by default. When enabled, each *text* block is sent to a local Ollama model
with a strict prompt that fixes only obvious OCR artefacts — especially umlaut /
ß substitutions — without translating, rephrasing, or adding content. It NEVER
touches table structure, figures, or equations.

Runs entirely offline against ``127.0.0.1:11434`` and uses only the stdlib
(urllib), so it adds no dependency. If Ollama is unreachable it logs a warning
and leaves the text untouched.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import events
from .config import RunConfig
from .parse import Block

_PROMPT = (
    "Du korrigierst OCR-Fehler in deutschem Text. Korrigiere NUR offensichtliche "
    "Erkennungsfehler (falsche Zeichen, zerrissene Wörter, falsche Umlaute wie "
    "ae/oe/ue statt ä/ö/ü, falsches ß). Übersetze nicht, fasse nicht zusammen, "
    "formuliere nicht um und füge nichts hinzu. Gib ausschließlich den "
    "korrigierten Text zurück, ohne Erklärung.\n\n"
    "Text:\n{text}\n\nKorrigiert:"
)


def _generate(host: str, model: str, prompt: str, timeout: float = 60.0) -> str | None:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return (body.get("response") or "").strip()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _plausible(original: str, corrected: str) -> bool:
    """Reject wild rewrites — a correction should be close in length."""
    if not corrected:
        return False
    return len(corrected) <= 1.5 * len(original) + 40


def correct_blocks(blocks: list[Block], cfg: RunConfig) -> int:
    """Correct text blocks in place. Returns the number of blocks changed."""
    text_blocks = [b for b in blocks if b.is_text and len(b.text) >= 4]
    if not text_blocks:
        return 0

    # Probe once; if the first call fails, assume Ollama is down and stop.
    changed = 0
    for i, block in enumerate(text_blocks):
        out = _generate(cfg.ollama_host, cfg.correction_model, _PROMPT.format(text=block.text))
        if out is None:
            events.log(
                f"Ollama unreachable at {cfg.ollama_host}; skipping correction pass",
                "warning",
            )
            break
        if _plausible(block.text, out) and out != block.text:
            block.text = out
            changed += 1
        events.status(
            events.STAGE_PARSING,
            progress=0.85 + 0.1 * (i + 1) / len(text_blocks),
            detail=f"German correction {i + 1}/{len(text_blocks)}",
        )
    if changed:
        events.log(f"German correction adjusted {changed} block(s)")
    return changed
