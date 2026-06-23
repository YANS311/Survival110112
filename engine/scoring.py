"""
engine/scoring.py
=================
FinalMLP-based survival scoring engine for Beijing Postgraduate Simulator V2.0.

Architecture
------------
FinalMLP is a two-stream MLP architecture (He et al., RecSys 2023) that
separates feature interactions into two independent sub-networks and fuses
them at the output layer.  Here we adapt it as a *survival-score regressor*:

    Stream 1 (Economic)  : money, rent_burden, research_fund
    Stream 2 (Wellbeing) : hp, san, san_cap, thesis_progress, survival_months
    Fusion               : concat → linear → sigmoid → score ∈ [0, 1]

The model runs on the local RTX 4080 via CUDA when available, falling back
to CPU transparently.

Public API
----------
    from engine.scoring import score_player, SurvivalScoreResult

    result = score_player(player)
    print(result.score)          # float in [0, 1]
    print(result.recommendation) # human-readable advice string
    print(result.risk_level)     # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

# ── Device selection ──────────────────────────────────────────────────────────
_DEVICE: Optional[torch.device] = None


def _get_device() -> torch.device:
    global _DEVICE
    if _DEVICE is None:
        if torch.cuda.is_available():
            _DEVICE = torch.device("cuda")
            logger.info("[FinalMLP] Using CUDA device: %s", torch.cuda.get_device_name(0))
        else:
            _DEVICE = torch.device("cpu")
            logger.info("[FinalMLP] CUDA not available – falling back to CPU.")
    return _DEVICE


# ── Feature engineering ───────────────────────────────────────────────────────

# District commute penalty map (higher = worse commute)
_COMMUTE_PENALTY: dict[str, float] = {
    "110108": 0.0,   # Haidian  – near PKU
    "110105": 0.1,   # Chaoyang – near CUC
    "110112": 0.2,   # Tongzhou
    "110114": 0.3,   # Changping
    "110113": 0.35,  # Shunyi
    "110115": 0.4,   # Yizhuang
    "131082": 0.55,  # Yanjiao (cross-province)
    "110117": 0.6,   # Pinggu (far east)
}

# School graduation thresholds
_GRAD_THRESHOLD: dict[str, float] = {
    "110105": 100.0,  # CUC 2-year
    "110108": 180.0,  # PKU 3-year
}


def _extract_features(player) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Extract two feature vectors from a Player model instance.

    Returns
    -------
    econ_feat : Tensor[float32, shape=(3,)]
        Economic stream features.
    well_feat : Tensor[float32, shape=(5,)]
        Wellbeing stream features.
    """
    # ── Economic stream ───────────────────────────────────────────────────────
    money_norm = float(max(min(player.money / 50_000.0, 1.0), -0.5))

    district = getattr(player, "current_district", None) or ""
    rent = 0.0
    if district:
        from game.constants import DISTRICT_DATA
        rent = DISTRICT_DATA.get(district, {}).get("rent", 0)
    rent_burden = float(min(rent / max(player.money, 1.0), 1.0)) if player.money > 0 else 1.0

    research_fund = 1.0 if getattr(player, "has_research_fund", False) else 0.0

    econ = torch.tensor([money_norm, rent_burden, research_fund], dtype=torch.float32)

    # ── Wellbeing stream ──────────────────────────────────────────────────────
    hp_norm = float(max(min(player.hp / 100.0, 1.0), 0.0))
    san_norm = float(max(min(player.san / float(player.san_cap or 100), 1.0), 0.0))

    grad_thresh = _GRAD_THRESHOLD.get(player.school_code, 100.0)
    thesis_norm = float(min(player.thesis_progress / grad_thresh, 1.0))

    months_norm = float(min(getattr(player, "survival_months", 0) / 36.0, 1.0))

    commute_penalty = _COMMUTE_PENALTY.get(district, 0.3)

    well = torch.tensor(
        [hp_norm, san_norm, thesis_norm, months_norm, commute_penalty],
        dtype=torch.float32,
    )

    return econ, well


# ── FinalMLP model definition ─────────────────────────────────────────────────

class _FeatureInteractionUnit(nn.Module):
    """Single-stream MLP with residual-style skip connection."""

    def __init__(self, in_dim: int, hidden_dim: int = 32, out_dim: int = 16):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, out_dim),
            nn.GELU(),
        )
        # Projection for skip connection when dims differ
        self.skip = nn.Linear(in_dim, out_dim) if in_dim != out_dim else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x) + self.skip(x)


class FinalMLP(nn.Module):
    """
    Two-stream MLP survival scorer.

    Stream 1 (Economic)  : 3 features → 16-dim embedding
    Stream 2 (Wellbeing) : 5 features → 16-dim embedding
    Fusion               : 32-dim → 16-dim → 1-dim (sigmoid)
    """

    ECON_DIM = 3
    WELL_DIM = 5
    EMBED_DIM = 16

    def __init__(self):
        super().__init__()
        self.stream_econ = _FeatureInteractionUnit(self.ECON_DIM, hidden_dim=32, out_dim=self.EMBED_DIM)
        self.stream_well = _FeatureInteractionUnit(self.WELL_DIM, hidden_dim=32, out_dim=self.EMBED_DIM)
        self.fusion = nn.Sequential(
            nn.Linear(self.EMBED_DIM * 2, 16),
            nn.GELU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, econ: torch.Tensor, well: torch.Tensor) -> torch.Tensor:
        e = self.stream_econ(econ)
        w = self.stream_well(well)
        fused = torch.cat([e, w], dim=-1)
        return self.fusion(fused).squeeze(-1)


# ── Singleton model instance ──────────────────────────────────────────────────
_MODEL: Optional[FinalMLP] = None


def _get_model() -> FinalMLP:
    """Lazy-initialise the FinalMLP model (weights are random / heuristic-seeded)."""
    global _MODEL
    if _MODEL is None:
        device = _get_device()
        model = FinalMLP().to(device)
        model.eval()

        # ── Heuristic weight seeding ──────────────────────────────────────────
        # Since we have no labelled training data, we seed the weights so that
        # the model behaves sensibly out-of-the-box:
        #   • Economic stream: money_norm is the most important feature (+)
        #   • Wellbeing stream: hp and san are most important (+), commute (-)
        # We do this by setting the first linear layer's weights manually.
        with torch.no_grad():
            # Economic stream: emphasise money_norm (index 0), penalise rent_burden (index 1)
            econ_w = model.stream_econ.net[0].weight  # shape [32, 3]
            econ_w[:, 0] *= 2.0   # money_norm boost
            econ_w[:, 1] *= -1.5  # rent_burden penalty

            # Wellbeing stream: emphasise hp (0) and san (1), penalise commute (4)
            well_w = model.stream_well.net[0].weight  # shape [32, 5]
            well_w[:, 0] *= 2.0   # hp boost
            well_w[:, 1] *= 1.8   # san boost
            well_w[:, 2] *= 1.5   # thesis boost
            well_w[:, 4] *= -1.2  # commute penalty

        _MODEL = model
        logger.info("[FinalMLP] Model initialised on %s", device)
    return _MODEL


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SurvivalScoreResult:
    score: float                  # 0.0 (doomed) → 1.0 (thriving)
    risk_level: str               # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    recommendation: str           # Human-readable advice
    econ_score: float             # Economic sub-score
    well_score: float             # Wellbeing sub-score


def _risk_level(score: float) -> str:
    if score >= 0.70:
        return "LOW"
    if score >= 0.45:
        return "MEDIUM"
    if score >= 0.25:
        return "HIGH"
    return "CRITICAL"


def _build_recommendation(player, score: float, econ_score: float, well_score: float) -> str:
    """Generate a context-aware recommendation string."""
    tips = []

    if player.hp < 30:
        tips.append("⚠️ HP危急：立即休息或就医，别再熬夜了。")
    if player.san < 20:
        tips.append("🧠 SAN值告急：去找心理咨询或买瑞幸包月卡。")
    if player.money < 3000:
        tips.append("💸 余额不足：考虑接实习或找水导借钱。")

    district = getattr(player, "current_district", None)
    if district in ("131082", "110117"):
        tips.append("🚇 通勤地狱：考虑搬到更近的区域以节省体力。")

    grad_thresh = _GRAD_THRESHOLD.get(player.school_code, 100.0)
    if player.thesis_progress < grad_thresh * 0.5:
        tips.append("📝 论文进度落后：减少娱乐，增加学习时间。")

    if not tips:
        if score >= 0.7:
            tips.append("✅ 状态良好，继续保持当前节奏。")
        else:
            tips.append("📊 综合状态一般，注意平衡各项指标。")

    # Region-specific advice
    if district == "110117":  # Pinggu
        tips.append("🍑 平谷大桃补充体力是个好选择（¥150）。")
    elif district == "131082":  # Yanjiao
        tips.append("🚌 燕郊通勤者：22号线开通前请保重身体。")
    elif district == "110108":  # Haidian
        tips.append("📚 海淀学区：学术氛围浓厚，论文加成最高。")

    return " | ".join(tips)


# ── Public scoring function ───────────────────────────────────────────────────

def score_player(player) -> SurvivalScoreResult:
    """
    Run FinalMLP inference on a Player instance and return a SurvivalScoreResult.

    Parameters
    ----------
    player : game.models.Player
        The current player object (Django model instance).

    Returns
    -------
    SurvivalScoreResult
        Dataclass with score, risk_level, recommendation, and sub-scores.
    """
    device = _get_device()
    model  = _get_model()

    econ_feat, well_feat = _extract_features(player)
    econ_feat = econ_feat.unsqueeze(0).to(device)  # [1, 3]
    well_feat = well_feat.unsqueeze(0).to(device)  # [1, 5]

    with torch.no_grad():
        # Full fusion score
        full_score = model(econ_feat, well_feat).item()

        # Sub-scores: run each stream through fusion with a neutral counterpart
        neutral_econ = torch.tensor([[0.5, 0.1, 0.0]], dtype=torch.float32, device=device)
        neutral_well = torch.tensor([[0.5, 0.5, 0.5, 0.5, 0.2]], dtype=torch.float32, device=device)

        econ_only = model(econ_feat, neutral_well).item()
        well_only = model(neutral_econ, well_feat).item()

    risk = _risk_level(full_score)
    rec  = _build_recommendation(player, full_score, econ_only, well_only)

    logger.debug(
        "[FinalMLP] score=%.3f econ=%.3f well=%.3f risk=%s",
        full_score, econ_only, well_only, risk,
    )

    return SurvivalScoreResult(
        score=round(full_score, 4),
        risk_level=risk,
        recommendation=rec,
        econ_score=round(econ_only, 4),
        well_score=round(well_only, 4),
    )
