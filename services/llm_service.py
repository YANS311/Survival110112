"""
services/llm_service.py
=======================
Async LLM service for the Beijing Postgraduate Simulator V2.0.

Connects to a local Ollama instance running qwen3.5:0.8b and generates
a 50-word cyberpunk philosopher terminal monologue for every Game Over event.

Usage (async context):
    from services.llm_service import generate_game_over_monologue
    monologue = await generate_game_over_monologue(stats_dict)
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Ollama configuration ──────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "qwen3.5:0.8b"
OLLAMA_TIMEOUT  = 60.0          # seconds; local inference is fast on RTX 4080

# ── Prompt template ───────────────────────────────────────────────────────────
_MONOLOGUE_PROMPT = (
    "Based on these stats: {stats}, "
    "write a 50-word terminal monologue in the style of a cynical cyberpunk philosopher."
)


def _build_stats_string(stats: dict) -> str:
    """Convert a player-stats dict into a compact, human-readable string."""
    parts = []
    label_map = {
        "hp":               "HP",
        "san":              "SAN",
        "money":            "Money(¥)",
        "thesis_progress":  "Thesis%",
        "survival_months":  "Months",
        "ending_type":      "Ending",
        "current_district": "District",
        "school_code":      "School",
    }
    for key, label in label_map.items():
        if key in stats:
            val = stats[key]
            if isinstance(val, float):
                val = f"{val:.1f}"
            parts.append(f"{label}={val}")
    return ", ".join(parts) if parts else str(stats)


async def generate_game_over_monologue(
    stats: dict,
    *,
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    timeout: float = OLLAMA_TIMEOUT,
) -> str:
    """
    Call Ollama's /api/generate endpoint asynchronously and return the
    cyberpunk monologue text.

    Falls back to a hard-coded string if Ollama is unreachable or returns
    an error, so the game never crashes on LLM failure.

    Parameters
    ----------
    stats : dict
        Player stats snapshot, e.g. {"hp": 0, "san": 12, "money": 300, ...}
    model : str
        Ollama model tag (default: qwen3.5:0.8b)
    base_url : str
        Ollama server base URL (default: http://localhost:11434)
    timeout : float
        HTTP request timeout in seconds

    Returns
    -------
    str
        The generated monologue (or a fallback string on error).
    """
    stats_str = _build_stats_string(stats)
    prompt    = _MONOLOGUE_PROMPT.format(stats=stats_str)

    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.85,
            "top_p":       0.9,
            "num_predict": 120,   # ~50 English words / ~80 Chinese chars
        },
    }

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            monologue = data.get("response", "").strip()
            if not monologue:
                raise ValueError("Empty response from Ollama")
            logger.info("[LLM] Monologue generated (%d chars)", len(monologue))
            return monologue

    except httpx.ConnectError:
        logger.warning("[LLM] Ollama not reachable at %s – using fallback.", base_url)
    except httpx.TimeoutException:
        logger.warning("[LLM] Ollama request timed out after %.1fs – using fallback.", timeout)
    except Exception as exc:  # noqa: BLE001
        logger.error("[LLM] Unexpected error: %s – using fallback.", exc)

    return _fallback_monologue(stats)


def _fallback_monologue(stats: dict) -> str:
    """Return a deterministic fallback monologue when Ollama is unavailable."""
    ending = stats.get("ending_type", "UNKNOWN")
    hp     = stats.get("hp", 0)
    money  = stats.get("money", 0)

    if ending == "SLAYED_HP":
        return (
            "The body is just wetware running on borrowed time. "
            "Mine ran out at {hp:.0f} HP. "
            "The city doesn't mourn deprecated processes.".format(hp=hp)
        )
    if ending == "SLAYED_MONEY":
        return (
            "Capital is the only algorithm that never throws an exception. "
            "I had ¥{money:.0f} left when the stack overflowed.".format(money=money)
        )
    if ending == "SANHE_MASTER":
        return (
            "Sanity is a social construct enforced by the academic-industrial complex. "
            "I opted out. The neon signs still blink. I just stopped reading them."
        )
    if ending in ("GRADUATED", "PHD"):
        return (
            "They handed me a certificate and called it victory. "
            "I called it a receipt for three years of RAM I'll never get back."
        )
    return (
        "Every process terminates. Mine just happened to terminate "
        "before the thesis compiled. The kernel doesn't care. Neither do I."
    )


# ── Synchronous wrapper for non-async Django views ───────────────────────────

def generate_game_over_monologue_sync(stats: dict) -> str:
    """
    Synchronous wrapper around the async function.
    Safe to call from standard Django views (non-ASGI context).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an already-running event loop (e.g. django-ninja async view).
            # Callers should use the async version directly in that case.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, generate_game_over_monologue(stats))
                return future.result(timeout=OLLAMA_TIMEOUT + 5)
        else:
            return loop.run_until_complete(generate_game_over_monologue(stats))
    except Exception as exc:  # noqa: BLE001
        logger.error("[LLM] Sync wrapper error: %s", exc)
        return _fallback_monologue(stats)
