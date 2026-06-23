"""
game/views_v2.py
================
Refactored views using the Strategy Pattern for survival regions.

Strategy Pattern Implementation
--------------------------------
Each survival region (Haidian, Pinggu, Yanjiao, and a default) is encapsulated
in a RegionStrategy class that defines:
  - region_name()       : display name
  - commute_warning()   : region-specific commute warning message
  - hp_drain_modifier() : multiplier applied to base HP drain
  - san_drain_modifier(): multiplier applied to base SAN drain
  - special_event()     : optional region-specific random event (returns msg or None)

The `get_region_strategy(district_code)` factory returns the correct strategy.

LLM Integration
---------------
The `game_over` view now calls `services.llm_service.generate_game_over_monologue_sync`
to generate a cyberpunk philosopher monologue via qwen3.5:0.8b on every Game Over.
The result is passed to the template as `llm_monologue`.

The original `heartbreaking_quote` (hand-crafted) is still passed alongside it,
so the template can display both or choose one.
"""

from __future__ import annotations

import random
import logging
from abc import ABC, abstractmethod
from datetime import timedelta, date
from typing import Optional

from django.contrib import messages
from django.shortcuts import render, redirect

from .models import Player
from .constants import LEISURE_SPOTS, DISTRICT_DATA, MONTHLY_SETTLEMENTS, INTERN_SPOTS

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY PATTERN — Region Strategies
# ══════════════════════════════════════════════════════════════════════════════

class RegionStrategy(ABC):
    """Abstract base strategy for a survival region."""

    @abstractmethod
    def region_name(self) -> str: ...

    @abstractmethod
    def commute_warning(self) -> str: ...

    @abstractmethod
    def hp_drain_modifier(self) -> float: ...

    @abstractmethod
    def san_drain_modifier(self) -> float: ...

    def special_event(self, player: Player) -> Optional[str]:
        """Return a special event message, or None if no event fires."""
        return None


class HaidianStrategy(RegionStrategy):
    """
    海淀 (Haidian) — Academic heartland, near PKU.
    High rent, high thesis multiplier, moderate commute.
    """

    def region_name(self) -> str:
        return "海淀 · 中关村"

    def commute_warning(self) -> str:
        return "📚 海淀学区：学术氛围浓厚，但房租让你的钱包每月哭泣。"

    def hp_drain_modifier(self) -> float:
        return 0.8   # Near campus → less physical toll

    def san_drain_modifier(self) -> float:
        return 1.1   # Academic pressure is real

    def special_event(self, player: Player) -> Optional[str]:
        if random.random() < 0.08:
            bonus = round(random.uniform(2.0, 5.0), 2)
            player.thesis_progress += bonus
            player.save(update_fields=["thesis_progress"])
            return f"🔬 你在中关村偶遇了一位大牛，聊了两小时，论文进度 +{bonus}%！"
        return None


class PingguStrategy(RegionStrategy):
    """
    平谷 (Pinggu) — Far east suburb, peach country.
    Cheap rent, brutal commute, but peaches restore HP.
    """

    def region_name(self) -> str:
        return "平谷 · 桃花源"

    def commute_warning(self) -> str:
        return "🍑 平谷通勤者：852路公交车是你的第二个家，但沿途桃林让人心旷神怡。"

    def hp_drain_modifier(self) -> float:
        return 1.6   # Very long commute

    def san_drain_modifier(self) -> float:
        return 0.9   # Nature scenery slightly soothes the soul

    def special_event(self, player: Player) -> Optional[str]:
        if random.random() < 0.12:
            hp_gain = random.randint(5, 12)
            player.hp = min(100.0, player.hp + hp_gain)
            player.save(update_fields=["hp"])
            return f"🍑 路边摊大妈送了你一袋平谷大桃，HP +{hp_gain}！"
        return None


class YanjiaoStrategy(RegionStrategy):
    """
    燕郊 (Yanjiao) — Cross-province commute, cheapest rent, highest risk.
    The ultimate survival challenge: cross the checkpoint every day.
    """

    def region_name(self) -> str:
        return "燕郊 · 跨省生存"

    def commute_warning(self) -> str:
        return "🚌 燕郊通勤者：白庙检查站的队伍比你的论文还长，请保重身体。"

    def hp_drain_modifier(self) -> float:
        return 2.0   # Cross-province commute is brutal

    def san_drain_modifier(self) -> float:
        return 1.4   # Checkpoint anxiety is real

    def special_event(self, player: Player) -> Optional[str]:
        # Random checkpoint delay event
        if random.random() < 0.15:
            hp_loss = random.randint(3, 8)
            player.hp = max(0.0, player.hp - hp_loss)
            player.save(update_fields=["hp"])
            return (
                f"🚧 白庙检查站今天大排查，你在路上多耗了2小时，HP -{hp_loss}。"
            )
        # 22号线opening hype
        if random.random() < 0.05:
            san_gain = random.randint(5, 15)
            player.san = min(float(player.san_cap), player.san + san_gain)
            player.save(update_fields=["san"])
            return f"🚇 22号线施工进度更新！你对未来充满希望，SAN +{san_gain}。"
        return None


class DefaultRegionStrategy(RegionStrategy):
    """
    Fallback strategy for all other districts (Chaoyang, Tongzhou, Changping,
    Shunyi, Yizhuang, or homeless).
    """

    def __init__(self, district_code: str = ""):
        self._code = district_code

    def region_name(self) -> str:
        dist = DISTRICT_DATA.get(self._code)
        return dist["name"] if dist else "未知区域"

    def commute_warning(self) -> str:
        dist = DISTRICT_DATA.get(self._code)
        if dist:
            return f"🚇 {dist['name']}通勤中：{dist['vibe']}。"
        return "🏙️ 北京的地铁永远比你想象的更拥挤。"

    def hp_drain_modifier(self) -> float:
        # Moderate modifiers based on known district distances
        modifiers = {
            "110105": 0.9,   # Chaoyang – near CUC
            "110112": 1.0,   # Tongzhou
            "110114": 1.2,   # Changping
            "110113": 1.3,   # Shunyi
            "110115": 1.4,   # Yizhuang
        }
        return modifiers.get(self._code, 1.0)

    def san_drain_modifier(self) -> float:
        return 1.0

    def special_event(self, player: Player) -> Optional[str]:
        # Shunyi airport view event
        if self._code == "110113" and random.random() < 0.10:
            san_gain = random.randint(5, 10)
            player.san = min(float(player.san_cap), player.san + san_gain)
            player.save(update_fields=["san"])
            return f"✈️ 你看着顺义机场的飞机起降，暂时忘掉了论文的压力，SAN +{san_gain}。"
        return None


# ── Strategy factory ──────────────────────────────────────────────────────────

def get_region_strategy(district_code: Optional[str]) -> RegionStrategy:
    """
    Factory function: return the appropriate RegionStrategy for a district code.

    Parameters
    ----------
    district_code : str | None
        The player's current_district value (e.g. "110108", "110117", "131082").

    Returns
    -------
    RegionStrategy
        Concrete strategy instance.
    """
    if district_code == "110108":
        return HaidianStrategy()
    if district_code == "110117":
        return PingguStrategy()
    if district_code == "131082":
        return YanjiaoStrategy()
    return DefaultRegionStrategy(district_code or "")


# ══════════════════════════════════════════════════════════════════════════════
# HELPER UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def get_current_player() -> Optional[Player]:
    return Player.objects.first()


# ══════════════════════════════════════════════════════════════════════════════
# GAME OVER VIEW — with LLM integration
# ══════════════════════════════════════════════════════════════════════════════

def _build_player_stats(player: Player) -> dict:
    """Build a stats dict for the LLM service."""
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


def get_heartbreaking_quote(player: Player) -> Optional[str]:
    """
    Select a hand-crafted heartbreaking quote based on player state.
    (Preserved from original views.py — unchanged logic.)
    """
    from .constants import HEARTBREAKING_QUOTES

    if player.ending_type in ("GRADUATED", "PHD") and player.current_district == "110113":
        return (
            "你走出俸伯站，手里攥着那张沉甸甸的纸。远处顺义机场的飞机划过长空，"
            "那一刻你觉得，15 号线不仅通往朝阳，也通往你的未来。"
        )
    if player.ending_type == "LAST_MILE_MIRACLE":
        return (
            "你在俸伯站的寒风中晕倒，好心的外卖骑手把你送进了顺义区医院。"
            "你在病床上用颤抖的手点击了'提交'，那 0.69% 的缺憾被导师手动填补了。"
        )
    if player.ending_type == "THORNY_DIPLOMA":
        return (
            "虽然你的实验数据还差一组对照，但你凭借满格的理智在答辩现场舌战群儒，"
            "导师含泪给你签了字。"
        )
    if player.ending_type not in ("SLAYED_HP",):
        return None

    quotes_pool: list[str] = []
    if player.current_district and player.current_district in HEARTBREAKING_QUOTES:
        quotes_pool.extend(HEARTBREAKING_QUOTES[player.current_district])
    if player.thesis_progress > 80:
        quotes_pool.extend(HEARTBREAKING_QUOTES.get("high_thesis_low_hp", []))
    quotes_pool.extend(HEARTBREAKING_QUOTES.get("general", []))

    return random.choice(quotes_pool) if quotes_pool else "你的代码还能跑，你却跑不动了。"


def game_over(request):
    """
    Game Over view — V2.0 with LLM monologue.

    Calls qwen3.5:0.8b via Ollama to generate a cyberpunk philosopher
    monologue, displayed alongside the hand-crafted heartbreaking quote.
    """
    player = get_current_player()
    if not player or not player.is_game_over:
        return redirect("dashboard")

    heartbreaking_quote = get_heartbreaking_quote(player)

    # ── LLM monologue ─────────────────────────────────────────────────────────
    llm_monologue: Optional[str] = None
    try:
        from services.llm_service import generate_game_over_monologue_sync
        stats = _build_player_stats(player)
        llm_monologue = generate_game_over_monologue_sync(stats)
        logger.info("[GameOver] LLM monologue generated for player %s", player.pk)
    except Exception as exc:
        logger.error("[GameOver] LLM call failed: %s", exc)

    # ── Region strategy context ───────────────────────────────────────────────
    strategy = get_region_strategy(player.current_district)

    # ── FinalMLP score (best-effort) ──────────────────────────────────────────
    survival_score = None
    try:
        from engine.scoring import score_player
        survival_score = score_player(player)
    except Exception as exc:
        logger.warning("[GameOver] FinalMLP scoring failed: %s", exc)

    return render(request, "game/game_over.html", {
        "player":             player,
        "heartbreaking_quote": heartbreaking_quote,
        "llm_monologue":      llm_monologue,
        "region_strategy":    strategy,
        "survival_score":     survival_score,
    })


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD VIEW — with Strategy Pattern region context
# ══════════════════════════════════════════════════════════════════════════════

def dashboard(request):
    """
    Dashboard view — V2.0.

    Injects region strategy context and FinalMLP score into the template.
    Commute warning and special events are driven by the Strategy Pattern.
    """
    player = get_current_player()
    if not player:
        return redirect("init_game")

    # ── Thank-you moment check ────────────────────────────────────────────────
    thank_you_response = _check_thank_you_moment(request, player)
    if thank_you_response:
        return thank_you_response

    # ── Souvenir details ──────────────────────────────────────────────────────
    owned_ids = player.souvenirs_list
    owned_items = [LEISURE_SPOTS[sid] for sid in owned_ids if sid in LEISURE_SPOTS]

    # ── Renewal crisis ────────────────────────────────────────────────────────
    renewal_data = None
    if getattr(player, "is_in_renewal_crisis", False):
        from .constants import DISTRICT_RENEWAL_CRISIS
        renewal_data = DISTRICT_RENEWAL_CRISIS.get(player.current_district)

    # ── Homeless warnings ─────────────────────────────────────────────────────
    is_truly_homeless = player.is_homeless()
    if player.school_code == "110105" and not player.is_dorm_cleared:
        is_truly_homeless = False

    if is_truly_homeless:
        messages.warning(request, "⚠️ 你正处于流浪状态！由于缺乏睡眠和安全感，HP 正在大幅下降。")

    if (player.school_code == "110105"
            and player.current_month.year == 2026
            and player.current_month.month == 7):
        messages.error(request, "🚨 宿管通知：本月底将进行宿舍清场，请 110105 的同学抓紧寻找住处！")

    if player.is_game_over:
        return render(request, "game/game_over.html", {"player": player})

    # ── Region strategy ───────────────────────────────────────────────────────
    strategy = get_region_strategy(player.current_district)

    # Fire special event (modifies player in-place if triggered)
    special_event_msg = strategy.special_event(player)
    if special_event_msg:
        messages.info(request, special_event_msg)

    # Commute warning (shown as info message)
    if player.current_district:
        messages.info(request, strategy.commute_warning())

    # Commute buffer message from middleware
    commute_msg = request.session.pop("_commute_msg", None)
    if commute_msg:
        messages.warning(request, commute_msg)

    # ── Settlement data ───────────────────────────────────────────────────────
    current_month_idx = player.current_month.month
    settlement_data = MONTHLY_SETTLEMENTS.get(current_month_idx, MONTHLY_SETTLEMENTS[1])

    # ── Distance info (reuse existing logic from original views.py) ───────────
    distance_info = _calculate_distance_info(player)

    # ── FinalMLP score (best-effort, non-blocking) ────────────────────────────
    survival_score = None
    try:
        from engine.scoring import score_player
        survival_score = score_player(player)
    except Exception as exc:
        logger.warning("[Dashboard] FinalMLP scoring failed: %s", exc)

    context = {
        "player":          player,
        "settlement_data": settlement_data,
        "owned_souvenirs": owned_items,
        "renewal_data":    renewal_data,
        "risk_resistance": getattr(player, "risk_resistance", 50),
        "distance_info":   distance_info,
        "region_strategy": strategy,
        "survival_score":  survival_score,
    }
    return render(request, "game/dashboard.html", context)


# ══════════════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _check_thank_you_moment(request, player: Player):
    """Check if the thank-you moment should be triggered."""
    if player.school_code == "110105":
        if player.thesis_progress > 90.0 and player.san < 15.0:
            return render(request, "game/thank_you_moment.html", {"player": player})
    elif player.school_code == "110108":
        if player.thesis_progress > 160.0 and player.san < 18.0:
            return render(request, "game/thank_you_moment.html", {"player": player})
    return None


def _calculate_distance_info(player: Player) -> Optional[dict]:
    """Calculate commute distance info for the dashboard."""
    if not player.current_district:
        return None

    school_coordinates = {
        "110105": {"lng": 116.549348, "lat": 39.917044},
        "110108": {"lng": 116.311188, "lat": 39.992236},
    }
    district_coordinates = {
        "110108": {"lng": 116.311188, "lat": 39.992236},
        "110105": {"lng": 116.549348, "lat": 39.917044},
        "110112": {"lng": 116.656435, "lat": 39.902645},
        "110114": {"lng": 116.326222, "lat": 40.078594},
        "110113": {"lng": 116.653519, "lat": 40.123456},
        "131082": {"lng": 116.813822, "lat": 39.953632},
        "110115": {"lng": 116.493519, "lat": 39.723456},
        "110117": {"lng": 117.123456, "lat": 40.123456},
    }

    if (player.school_code not in school_coordinates
            or player.current_district not in district_coordinates):
        return None

    import math
    sc = school_coordinates[player.school_code]
    dc = district_coordinates[player.current_district]

    R = 6371000
    lat1 = math.radians(sc["lat"])
    lat2 = math.radians(dc["lat"])
    dlat = math.radians(dc["lat"] - sc["lat"])
    dlng = math.radians(dc["lng"] - sc["lng"])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    distance = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    duration = int(distance / 30000 * 3600)

    distance_str = f"{distance / 1000:.1f}公里" if distance >= 1000 else f"{distance:.0f}米"
    if duration >= 3600:
        h, m = duration // 3600, (duration % 3600) // 60
        duration_str = f"约{h}小时{m}分钟"
    else:
        duration_str = f"约{duration // 60}分钟"

    return {
        "distance":     int(distance),
        "duration":     duration,
        "distance_str": distance_str,
        "duration_str": duration_str,
    }
