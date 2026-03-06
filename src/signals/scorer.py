# /src/signals/scorer.py
"""
APEX Scalper — Confluence Scorer
===================================
Aggregates scores from all four signal modules (A–D) plus the HTF bias bonus (E)
into a single weighted confluence score (0–10).

Scoring table:
    Module A — Momentum         max 2.0 pts
    Module B — Mean Reversion   max 2.0 pts
    Module C — Order Flow       max 2.0 pts
    Module D — SMC / Liquidity  max 2.0 pts
    Module E — HTF Bias Bonus   max 2.0 pts
    ─────────────────────────────────────────
    TOTAL                       max 10.0 pts

Rules:
    - Modules A and B are DIRECTIONALLY OPPOSED by design.
      Only the module whose direction aligns with the final call contributes.
    - If no directional consensus across ≥2 modules → no trade.
    - Final score determines position size tier.
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from config.settings import MIN_SCORE_TO_TRADE, SCORE_SIZE_TIERS
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SignalResult:
    """
    Structured output from the scorer — passed to the risk engine.
    """
    tradeable:   bool   = False
    direction:   str    = "neutral"    # "long" | "short"
    score:       float  = 0.0          # 0.0–10.0
    size_mult:   float  = 0.0          # Position size multiplier from tier
    instrument:  str    = ""
    timestamp:   object = None

    # Per-module scores for logging
    momentum_score:      float = 0.0
    mean_rev_score:      float = 0.0
    order_flow_score:    float = 0.0
    smc_score:           float = 0.0
    htf_score:           float = 0.0

    # Module directions (for transparency)
    momentum_dir:     str = "neutral"
    mean_rev_dir:     str = "neutral"
    order_flow_dir:   str = "neutral"
    smc_dir:          str = "neutral"
    htf_bias:         str = "neutral"

    reason:    str = ""
    detail:    str = ""


class ConflueceScorer:
    """
    Aggregates all module outputs into a final trade signal.
    Handles directional conflict resolution and score weighting.
    """

    def evaluate(
        self,
        instrument:       str,
        timestamp:        object,
        momentum_result:  dict,
        mean_rev_result:  dict,
        order_flow_result:dict,
        smc_result:       dict,
        htf_result:       dict,
        regime:           str,     # "trending" | "ranging"
    ) -> SignalResult:
        """
        Combine all module results into a final confluence score and signal.

        Regime-aware weighting:
            Trending  → boost momentum + SMC modules
            Ranging   → boost mean reversion + order flow modules

        Args:
            instrument:        Oanda symbol
            timestamp:         Current bar datetime
            momentum_result:   Output from MomentumSignal.evaluate()
            mean_rev_result:   Output from MeanReversionSignal.evaluate()
            order_flow_result: Output from OrderFlowSignal.evaluate()
            smc_result:        Output from SMCSignal.evaluate()
            htf_result:        Output from HTFBias.evaluate()
            regime:            Current market regime from RegimeFilter

        Returns:
            SignalResult dataclass
        """
        sig = SignalResult(instrument=instrument, timestamp=timestamp)

        # Extract individual module scores and directions
        sig.momentum_score   = momentum_result.get("score", 0.0)
        sig.mean_rev_score   = mean_rev_result.get("score", 0.0)
        sig.order_flow_score = order_flow_result.get("score", 0.0)
        sig.smc_score        = smc_result.get("score", 0.0)
        sig.htf_score        = htf_result.get("score", 0.0)

        sig.momentum_dir   = momentum_result.get("direction", "neutral")
        sig.mean_rev_dir   = mean_rev_result.get("direction", "neutral")
        sig.order_flow_dir = order_flow_result.get("direction", "neutral")
        sig.smc_dir        = smc_result.get("direction", "neutral")
        sig.htf_bias       = htf_result.get("bias", "neutral")

        # ── STEP 1: DIRECTIONAL VOTE ──────────────────────────────────────
        # Collect all non-neutral directional votes
        all_signals = [
            sig.momentum_dir, sig.mean_rev_dir,
            sig.order_flow_dir, sig.smc_dir, sig.htf_bias
        ]
        long_votes  = sum(1 for d in all_signals if d == "long")
        short_votes = sum(1 for d in all_signals if d == "short")

        # Need consensus from at least 2 modules to form a direction
        if long_votes > short_votes and long_votes >= 2:
            final_direction = "long"
        elif short_votes > long_votes and short_votes >= 2:
            final_direction = "short"
        else:
            sig.reason = (
                f"No directional consensus — "
                f"Long votes: {long_votes} | Short votes: {short_votes}"
            )
            return sig   # tradeable=False, score=0.0

        # ── STEP 2: DIRECTION-ALIGNED SCORE AGGREGATION ───────────────────
        # Only count module scores if they AGREE with the final direction
        # This prevents opposite-direction partial scores polluting the total

        def score_if_aligned(module_score, module_dir):
            """Return score only if module direction aligns with final direction."""
            if module_dir == final_direction:
                return module_score
            return 0.0

        aligned_momentum   = score_if_aligned(sig.momentum_score,   sig.momentum_dir)
        aligned_mean_rev   = score_if_aligned(sig.mean_rev_score,   sig.mean_rev_dir)
        aligned_order_flow = score_if_aligned(sig.order_flow_score, sig.order_flow_dir)
        aligned_smc        = score_if_aligned(sig.smc_score,        sig.smc_dir)

        # HTF bonus always contributes if it aligns (or is neutral — neutral gets 0)
        htf_bonus = sig.htf_score if sig.htf_bias == final_direction else 0.0

        # ── STEP 3: REGIME-BASED WEIGHTING ───────────────────────────────
        # In trending markets, we boost momentum and SMC
        # In ranging markets, we boost mean reversion and order flow
        if regime == "trending":
            regime_multipliers = {
                "momentum":   1.2,   # 20% boost in trending
                "mean_rev":   0.8,   # 20% discount — counter-trend risky in trend
                "order_flow": 1.0,
                "smc":        1.1,
            }
        else:  # ranging
            regime_multipliers = {
                "momentum":   0.9,
                "mean_rev":   1.2,   # 20% boost in ranging — mean rev is ideal
                "order_flow": 1.1,
                "smc":        1.0,
            }

        weighted_score = (
            aligned_momentum   * regime_multipliers["momentum"]   +
            aligned_mean_rev   * regime_multipliers["mean_rev"]   +
            aligned_order_flow * regime_multipliers["order_flow"] +
            aligned_smc        * regime_multipliers["smc"]        +
            htf_bonus                                              # No multiplier on HTF bonus
        )

        # Cap at 10.0 regardless of multipliers
        final_score = round(min(weighted_score, 10.0), 2)

        # ── STEP 4: MINIMUM SCORE GATE ────────────────────────────────────
        if final_score < MIN_SCORE_TO_TRADE:
            sig.score   = final_score
            sig.reason  = (
                f"Score {final_score:.1f} below minimum threshold of {MIN_SCORE_TO_TRADE}"
            )
            return sig   # tradeable=False

        # ── STEP 5: POSITION SIZE TIER ────────────────────────────────────
        size_mult = self._get_size_multiplier(final_score)

        # ── FINAL SIGNAL ──────────────────────────────────────────────────
        sig.tradeable  = True
        sig.direction  = final_direction
        sig.score      = final_score
        sig.size_mult  = size_mult
        sig.reason     = "TRADE SIGNAL CONFIRMED"
        sig.detail     = (
            f"[{instrument}] {final_direction.upper()} | "
            f"Score: {final_score:.1f}/10 | "
            f"Regime: {regime} | "
            f"Modules — Mom: {aligned_momentum:.1f} | "
            f"MR: {aligned_mean_rev:.1f} | "
            f"OF: {aligned_order_flow:.1f} | "
            f"SMC: {aligned_smc:.1f} | "
            f"HTF: {htf_bonus:.1f} | "
            f"SizeMult: {size_mult}x"
        )

        logger.info(sig.detail)
        return sig

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _get_size_multiplier(self, score: float) -> float:
        """
        Map a confluence score to a position size multiplier using SCORE_SIZE_TIERS.

        Args:
            score: Confluence score 0.0–10.0

        Returns:
            Size multiplier: 0.5 | 0.75 | 1.0
        """
        for (lo, hi), mult in SCORE_SIZE_TIERS.items():
            if lo <= score <= hi:
                return mult
        # Score > 8 falls through — return max multiplier
        return max(SCORE_SIZE_TIERS.values())