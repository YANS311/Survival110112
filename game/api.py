"""
game/api.py
===========
Django-Ninja async API for Beijing Postgraduate Simulator V2.0.

Endpoints
---------
GET  /api/player/status          → current player stats snapshot
GET  /api/player/score           → FinalMLP survival score + recommendation
POST /api/player/game-over-llm   → trigger LLM monologue for current game-over state
POST /api/action/study           → async study action
POST /api/action/rest            → async rest action
POST /api/action/settle          → trigger month settlement (async)

Mount in core/urls.py:
    from game.api import api as game_api
    urlpatterns += [path("api/", game_api.urls)]
"""

from __future__ import annotations

import logging
from typing import Optional

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

logger = logging.getLogger(__name__)

# ── API instance ──────────────────────────────────────────────────────────────
api = NinjaAPI(
    title="Beijing Postgraduate Simulator API",
    version="2.0.0",
    description=(
        "High-performance async API for the Cyber-Reality Edition. "
        "Powered by django-ninja + Uvicorn ASGI."
    ),
    urls_namespace="game_api",
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlayerStatusOut(Schema):
    player_id: int
    school_code: str
    current_month: str
    hp: float
    san: float
    san_cap: int
    money: float
    thesis_progress: float
    survival_months: int
    current_district: Optional[str]
    display_location: str
    risk_resistance: float
    is_game_over: bool
    ending_type: Optional[str]


class SurvivalScoreOut(Schema):
    score: float
    risk_level: str
    recommendation: str
    econ_score: float
    well_score: float


class LLMMonologueOut(Schema):
    monologue: str
    model: str
    stats_used: dict


class ActionResultOut(Schema):
    success: bool
    message: str
    hp: float
    san: float
    money: float
    thesis_progress: float


class ErrorOut(Schema):
    detail: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_player():
    """Fetch the singleton player or raise 404."""
    from game.models import Player
    player = Player.objects.first()
    if not player:
        raise HttpError(404, "No active player found. Start a new game first.")
    return player


def _player_stats_dict(player) -> dict:
    """Build a stats dict suitable for the LLM prompt."""
    return {
        "hp":               player.hp,
        "san":              player.san,
        "money":            player.money,
        "thesis_progress":  player.thesis_progress,
        "survival_months":  player.survival_months,
        "ending_type":      player.ending_type or "UNKNOWN",
        "current_district": player.current_district or "homeless",
        "school_code":      player.school_code,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@api.get(
    "/player/status",
    response=PlayerStatusOut,
    summary="Get current player status snapshot",
    tags=["Player"],
)
async def player_status(request: HttpRequest) -> PlayerStatusOut:
    """Return a full snapshot of the current player's stats."""
    from game.models import Player
    from asgiref.sync import sync_to_async

    get_player_async = sync_to_async(_get_player, thread_sensitive=True)
    player = await get_player_async()

    return PlayerStatusOut(
        player_id=player.pk,
        school_code=player.school_code,
        current_month=player.current_month.strftime("%Y-%m"),
        hp=player.hp,
        san=player.san,
        san_cap=player.san_cap,
        money=player.money,
        thesis_progress=player.thesis_progress,
        survival_months=player.survival_months,
        current_district=player.current_district,
        display_location=player.display_location,
        risk_resistance=player.risk_resistance,
        is_game_over=player.is_game_over,
        ending_type=player.ending_type,
    )


@api.get(
    "/player/score",
    response=SurvivalScoreOut,
    summary="Run FinalMLP inference and get survival score",
    tags=["AI Engine"],
)
async def player_score(request: HttpRequest) -> SurvivalScoreOut:
    """
    Run the FinalMLP model on the current player and return a survival score
    with risk level and personalised recommendation.
    """
    from asgiref.sync import sync_to_async
    from engine.scoring import score_player

    player = await sync_to_async(_get_player, thread_sensitive=True)()
    result = await sync_to_async(score_player, thread_sensitive=False)(player)

    return SurvivalScoreOut(
        score=result.score,
        risk_level=result.risk_level,
        recommendation=result.recommendation,
        econ_score=result.econ_score,
        well_score=result.well_score,
    )


@api.post(
    "/player/game-over-llm",
    response=LLMMonologueOut,
    summary="Generate LLM cyberpunk monologue for game-over state",
    tags=["AI Engine"],
)
async def game_over_llm(request: HttpRequest) -> LLMMonologueOut:
    """
    Call qwen3.5:0.8b via Ollama to generate a 50-word cyberpunk philosopher
    monologue based on the current player's terminal stats.

    The player does NOT need to be in game-over state to call this endpoint
    (useful for previewing / testing), but it is most meaningful when
    `is_game_over` is True.
    """
    from asgiref.sync import sync_to_async
    from services.llm_service import generate_game_over_monologue, OLLAMA_MODEL

    player = await sync_to_async(_get_player, thread_sensitive=True)()
    stats  = _player_stats_dict(player)

    monologue = await generate_game_over_monologue(stats)

    return LLMMonologueOut(
        monologue=monologue,
        model=OLLAMA_MODEL,
        stats_used=stats,
    )


@api.post(
    "/action/study",
    response=ActionResultOut,
    summary="Perform a study action (async)",
    tags=["Actions"],
)
async def action_study(request: HttpRequest) -> ActionResultOut:
    """
    Async study action: costs 45 SAN + 20 HP, gains 4–8% thesis progress.
    Mirrors the synchronous `study` view but exposed as a JSON API.
    """
    import random as _random
    from asgiref.sync import sync_to_async

    player = await sync_to_async(_get_player, thread_sensitive=True)()

    if player.san < 45 or player.hp < 20:
        return ActionResultOut(
            success=False,
            message="❌ SAN 或 HP 不足，无法进行高强度学术。",
            hp=player.hp,
            san=player.san,
            money=player.money,
            thesis_progress=player.thesis_progress,
        )

    gain = round(_random.uniform(4.0, 8.0), 2)
    player.san -= 45
    player.hp  -= 20
    player.thesis_progress += gain

    await sync_to_async(player.save, thread_sensitive=True)()

    building = "教四" if player.school_code == "110105" else "理科一号楼"
    return ActionResultOut(
        success=True,
        message=f"💻 在{building}肝了一夜代码，论文进度 +{gain}%！",
        hp=player.hp,
        san=player.san,
        money=player.money,
        thesis_progress=player.thesis_progress,
    )


@api.post(
    "/action/rest",
    response=ActionResultOut,
    summary="Perform a rest action (async)",
    tags=["Actions"],
)
async def action_rest(request: HttpRequest) -> ActionResultOut:
    """
    Async rest action: restores 15 HP (or penalises if homeless), costs 25 SAN.
    """
    from asgiref.sync import sync_to_async

    player = await sync_to_async(_get_player, thread_sensitive=True)()

    if player.is_homeless():
        player.hp  = max(0.0, player.hp - 15.0)
        player.san = min(player.san - 50.0, float(player.san_cap))
        msg = "😰 在街头躺平，没有宿舍的庇护，身心俱疲..."
    else:
        player.hp  = min(player.hp + 15.0, 100.0)
        player.san = min(player.san - 25.0, float(player.san_cap))
        msg = "🛏️ 你在宿舍床上躺平了整个周末，但命暂时保住了。"

    player.thesis_progress = max(0.0, player.thesis_progress - 5.0)
    await sync_to_async(player.save, thread_sensitive=True)()

    return ActionResultOut(
        success=True,
        message=msg,
        hp=player.hp,
        san=player.san,
        money=player.money,
        thesis_progress=player.thesis_progress,
    )


@api.get(
    "/health",
    summary="Health check",
    tags=["System"],
)
async def health_check(request: HttpRequest) -> dict:
    """Simple liveness probe for load balancers / monitoring."""
    return {"status": "ok", "version": "2.0.0", "engine": "uvicorn+asgi"}
