"""
game/middleware.py
==================
Survival Buffer Middleware — V2.0 Cyber-Reality Edition.

Randomly deducts HP from the player based on their real-world commute
distance every N requests, simulating the physical toll of Beijing's
notorious commute grind.

Logic
-----
- Commute distance is calculated via Haversine formula (same as logic.py).
- HP deduction probability and magnitude scale with distance:
    ≤ 5 km   → 5 % chance, 1–3 HP
    5–20 km  → 15 % chance, 2–6 HP
    20–40 km → 30 % chance, 4–10 HP
    > 40 km  → 50 % chance, 6–15 HP  (Yanjiao / Pinggu tier)
- The middleware only fires on GET requests to the dashboard to avoid
  double-penalising action POSTs.
- A session key `_commute_tick` throttles the effect to at most once per
  real-world minute (prevents rapid-fire refresh abuse).

Installation
------------
Add to MIDDLEWARE in settings.py (after SessionMiddleware):

    'game.middleware.SurvivalBufferMiddleware',
"""

import math
import random
import logging
import time

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# ── Coordinate tables (mirrors logic.py / views.py) ──────────────────────────
_SCHOOL_COORDS: dict[str, dict] = {
    "110105": {"lng": 116.549348, "lat": 39.917044},  # CUC
    "110108": {"lng": 116.311188, "lat": 39.992236},  # PKU
}

_DISTRICT_COORDS: dict[str, dict] = {
    "110108": {"lng": 116.311188, "lat": 39.992236},  # Haidian
    "110105": {"lng": 116.549348, "lat": 39.917044},  # Chaoyang
    "110112": {"lng": 116.656435, "lat": 39.902645},  # Tongzhou
    "110114": {"lng": 116.326222, "lat": 40.078594},  # Changping
    "110113": {"lng": 116.653519, "lat": 40.123456},  # Shunyi
    "131082": {"lng": 116.813822, "lat": 39.953632},  # Yanjiao
    "110115": {"lng": 116.493519, "lat": 39.723456},  # Yizhuang
    "110117": {"lng": 117.123456, "lat": 40.123456},  # Pinggu
}

# Throttle: minimum seconds between commute-tick events per session
_TICK_INTERVAL_SECONDS = 60


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """Return great-circle distance in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _commute_distance_km(school_code: str, district_code: str) -> float:
    """Return estimated commute distance in km, or 0 if unknown."""
    school = _SCHOOL_COORDS.get(school_code)
    district = _DISTRICT_COORDS.get(district_code)
    if not school or not district:
        return 0.0
    return _haversine_km(
        school["lng"], school["lat"],
        district["lng"], district["lat"],
    )


def _hp_deduction_params(distance_km: float) -> tuple[float, int, int]:
    """
    Return (probability, min_hp_loss, max_hp_loss) for a given commute distance.
    """
    if distance_km <= 5:
        return 0.05, 1, 3
    if distance_km <= 20:
        return 0.15, 2, 6
    if distance_km <= 40:
        return 0.30, 4, 10
    return 0.50, 6, 15   # Yanjiao / Pinggu tier


class SurvivalBufferMiddleware(MiddlewareMixin):
    """
    Intercepts dashboard GET requests and probabilistically deducts HP
    based on the player's commute distance.
    """

    def process_request(self, request):
        # Only fire on dashboard GETs
        if request.method != "GET":
            return None
        if not request.path.rstrip("/").endswith("dashboard"):
            return None

        # Throttle: at most once per _TICK_INTERVAL_SECONDS
        now = time.time()
        last_tick = request.session.get("_commute_tick", 0)
        if now - last_tick < _TICK_INTERVAL_SECONDS:
            return None

        # Lazy import to avoid circular imports at module load time
        try:
            from game.models import Player
            player = Player.objects.first()
        except Exception:
            return None

        if not player or player.is_game_over:
            return None

        # Determine commute distance
        district = getattr(player, "current_district", None)
        school   = getattr(player, "school_code", None)

        # CUC students in dorm have zero commute
        if school == "110105" and not getattr(player, "is_dorm_cleared", False):
            return None

        if not district or not school:
            return None

        distance_km = _commute_distance_km(school, district)
        if distance_km == 0:
            return None

        prob, hp_min, hp_max = _hp_deduction_params(distance_km)

        if random.random() < prob:
            deduction = random.randint(hp_min, hp_max)
            player.hp = round(max(0.0, player.hp - deduction), 2)
            player.save(update_fields=["hp"])

            request.session["_commute_tick"] = now
            request.session["_commute_msg"] = (
                f"🚇 通勤消耗：{distance_km:.1f}km 的通勤让你损失了 {deduction} HP。"
            )
            logger.debug(
                "[SurvivalBuffer] district=%s dist=%.1fkm prob=%.0f%% deducted=%d HP → hp=%.1f",
                district, distance_km, prob * 100, deduction, player.hp,
            )
        else:
            request.session["_commute_tick"] = now

        return None
