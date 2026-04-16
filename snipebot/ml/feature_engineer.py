"""
feature_engineer.py — SMC feature vectors for the Random Forest model.

Feature vector (8 features):
  0: market_structure_encoded  (0=ranging, 1=uptrend, 2=downtrend, 3=reversal)
  1: fib_zone_distance         (0.0 = inside zone; fractional distance outside)
  2: order_block_quality       (strength score; 0 if not at an OB)
  3: rvol                      (relative volume; current / 20-bar avg)
  4: atr_expansion_ratio       (fast ATR / slow ATR)
  5: liquidity_swept           (1.0 = sweep confirmed, 0.0 = not)
  6: session_score             (0=low, 1=medium, 2=high activity)
  7: ob_distance_pct           (|price - OB center| / price)
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

STRUCTURE_ENCODING = {
    "ranging":   0,
    "uptrend":   1,
    "downtrend": 2,
    "reversal":  3,
}

FEATURE_NAMES = [
    "market_structure_encoded",
    "fib_zone_distance",
    "order_block_quality",
    "rvol",
    "atr_expansion_ratio",
    "liquidity_swept",
    "session_score",
    "ob_distance_pct",
]


# ── Live feature vector ───────────────────────────────────────────────────────

def build_feature_vector(indicators: Dict[str, Any],
                          vix: float,
                          signal_time: Optional[datetime] = None) -> np.ndarray:
    """
    Build an 8-element feature vector from a live indicator dict.
    *vix* is accepted for API compatibility but not included in the vector
    (VIX is already a hard gate in strategy.py).
    """
    # Encode market structure
    trend  = indicators.get("market_structure", "ranging")
    choch  = indicators.get("choch", False)
    struct = "reversal" if choch else trend
    struct_enc = float(STRUCTURE_ENCODING.get(struct, 0))

    swept = 1.0 if indicators.get("liquidity_swept", False) else 0.0

    vec = np.array([
        struct_enc,
        float(indicators.get("fib_zone_distance",    1.0)),
        float(indicators.get("order_block_quality",  0.0)),
        float(indicators.get("rvol",                 1.0)),
        float(indicators.get("atr_expansion_ratio",  1.0)),
        swept,
        float(indicators.get("session_score",        0)),
        float(indicators.get("ob_distance_pct",      1.0)),
    ], dtype=np.float32)

    return vec


# ── Historical feature vector (from stored trade row) ────────────────────────

def build_features_from_trade_row(trade: Dict[str, Any]) -> Optional[np.ndarray]:
    """
    Reconstruct a feature vector from a stored SQLite trade row.
    Used when re-training the model from historical data.

    Column mapping (repurposed fields):
      macd_signal     → sweep_type  ('sell_side'/'buy_side'/None)
      volume_ratio    → rvol
      sr_zone_quality → ob_quality
      market_regime   → market_structure string
      rsi_at_entry    → atr_expansion_ratio (stored if available, else 1.0)
    """
    try:
        regime    = trade.get("market_regime", "ranging") or "ranging"
        choch_ish = regime == "reversal"
        struct    = "reversal" if choch_ish else regime
        struct_enc = float(STRUCTURE_ENCODING.get(struct, 0))

        sweep_type = trade.get("macd_signal")
        swept = 1.0 if sweep_type in ("sell_side", "buy_side") else 0.0

        vec = np.array([
            struct_enc,
            0.0,                                             # fib_zone_distance (not stored)
            float(trade.get("sr_zone_quality") or 0.0),     # ob_quality
            float(trade.get("volume_ratio")    or 1.0),     # rvol
            float(trade.get("rsi_at_entry")    or 1.0),     # atr_expansion_ratio
            swept,
            1.0,                                             # session_score (not stored)
            0.0,                                             # ob_distance_pct (not stored)
        ], dtype=np.float32)

        return vec
    except Exception as exc:
        logger.warning("Could not build feature vector from trade row: %s", exc)
        return None


# ── Training dataset builder ──────────────────────────────────────────────────

def build_training_dataset(trades: List[Dict[str, Any]]):
    """
    Build X (n_samples × 8) and y (n_samples,) from a list of trade dicts.
    Label: 1 = trade hit Take Profit, 0 = everything else.
    """
    X_rows, y_rows = [], []
    for trade in trades:
        vec = build_features_from_trade_row(dict(trade))
        if vec is None:
            continue
        label = 1 if (trade.get("outcome") == "win" and
                      trade.get("exit_reason") == "tp") else 0
        X_rows.append(vec)
        y_rows.append(label)

    if not X_rows:
        return (np.empty((0, len(FEATURE_NAMES)), dtype=np.float32),
                np.empty(0, dtype=np.int32))

    return np.vstack(X_rows), np.array(y_rows, dtype=np.int32)


# ── Rule-based cold-start scorer ──────────────────────────────────────────────

def rule_based_confidence(indicators: Dict[str, Any],
                           vix: float,
                           direction: str) -> float:
    """
    Weighted score used for the first *cold_start_trades* trades (before ML kicks in).

    Component weights:
      Market structure alignment  0.25
      Fibonacci zone confirmation 0.25
      Order block quality         0.20
      Relative volume             0.15
      ATR expansion               0.15
    """
    score = 0.0

    # 1. Market structure alignment (0.25)
    trend  = indicators.get("market_structure", "ranging")
    choch  = indicators.get("choch", False)
    struct_dir = indicators.get("structure_direction")
    if choch and ((direction == "call" and struct_dir == "bullish") or
                  (direction == "put"  and struct_dir == "bearish")):
        score += 0.25
    elif (direction == "call" and trend == "uptrend") or \
         (direction == "put"  and trend == "downtrend"):
        score += 0.20
    elif trend != "ranging":
        score += 0.10

    # 2. Fibonacci zone (0.25)
    if indicators.get("in_fib_zone", False):
        score += 0.25
    else:
        dist = indicators.get("fib_zone_distance", 1.0)
        score += max(0.0, (0.01 - dist) / 0.01) * 0.25

    # 3. Order block quality (0.20)
    ob_q = indicators.get("order_block_quality", 0.0)
    score += min(1.0, ob_q / 3.0) * 0.20   # normalise strength score

    # 4. RVOL (0.15)
    rvol = indicators.get("rvol", 1.0)
    rvol_score = min(1.0, (rvol - 1.0) / 1.5)
    score += max(0.0, rvol_score) * 0.15

    # 5. ATR expansion (0.15)
    atr_ratio = indicators.get("atr_expansion_ratio", 1.0)
    atr_score = min(1.0, (atr_ratio - 1.0) / 0.5)
    score += max(0.0, atr_score) * 0.15

    return round(min(score, 1.0), 4)
