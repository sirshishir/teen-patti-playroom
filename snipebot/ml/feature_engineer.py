"""
feature_engineer.py — Build feature vectors from raw trade data and indicators.

Feature vector (8 features):
  0: RSI value at signal time
  1: MACD histogram value
  2: Volume ratio (current / 20-day avg)
  3: Distance from S/R zone center (as % of price)
  4: VIX at signal time
  5: Hour of day (int 9–15)
  6: Day of week (int 0–4)
  7: Market regime encoded (0=ranging, 1=trending, 2=volatile)
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REGIME_ENCODING = {"ranging": 0, "trending": 1, "volatile": 2}
FEATURE_NAMES = [
    "rsi",
    "macd_histogram",
    "volume_ratio",
    "sr_zone_distance_pct",
    "vix",
    "hour_of_day",
    "day_of_week",
    "market_regime_encoded",
]


def build_feature_vector(indicators: Dict[str, Any],
                         vix: float,
                         signal_time: Optional[datetime] = None) -> np.ndarray:
    """
    Build a single feature vector (shape [8,]) from indicator dict and VIX.

    Parameters
    ----------
    indicators  : Output of indicators.compute_all_indicators()
    vix         : VIX value at signal time
    signal_time : datetime of signal; uses UTC now if None
    """
    if signal_time is None:
        signal_time = datetime.utcnow()

    regime_enc = REGIME_ENCODING.get(indicators.get("market_regime", "ranging"), 0)

    vec = np.array([
        float(indicators.get("rsi", 50.0)),
        float(indicators.get("macd_histogram", 0.0)),
        float(indicators.get("volume_ratio", 1.0)),
        float(indicators.get("sr_zone_distance_pct", 0.0)),
        float(vix) if vix is not None else 15.0,
        float(signal_time.hour),
        float(signal_time.weekday()),
        float(regime_enc),
    ], dtype=np.float32)

    return vec


def build_features_from_trade_row(trade: Dict[str, Any]) -> Optional[np.ndarray]:
    """
    Reconstruct a feature vector from a stored trade row (SQLite Row / dict).
    Used when training the model from historical trades.
    """
    try:
        entry_date = trade.get("entry_date", "")
        if entry_date:
            dt = datetime.fromisoformat(str(entry_date))
        else:
            dt = datetime.utcnow()

        regime_enc = REGIME_ENCODING.get(trade.get("market_regime", "ranging"), 0)

        vec = np.array([
            float(trade.get("rsi_at_entry") or 50.0),
            0.0,  # MACD histogram not stored separately — use 0 for historical
            float(trade.get("volume_ratio") or 1.0),
            float(trade.get("sr_zone_quality") or 0.0),  # quality as proxy for distance
            float(trade.get("vix_at_entry") or 15.0),
            float(dt.hour),
            float(dt.weekday()),
            float(regime_enc),
        ], dtype=np.float32)

        return vec
    except Exception as exc:
        logger.warning("Could not build feature vector from trade: %s", exc)
        return None


def build_training_dataset(trades: List[Dict[str, Any]]):
    """
    Build X (feature matrix) and y (binary labels) from a list of trade dicts.

    Returns
    -------
    X : np.ndarray of shape (n_samples, 8)
    y : np.ndarray of shape (n_samples,) — 1=win (tp hit), 0=loss
    """
    X_rows = []
    y_rows = []

    for trade in trades:
        vec = build_features_from_trade_row(dict(trade))
        if vec is None:
            continue
        outcome = trade.get("outcome", "")
        exit_reason = trade.get("exit_reason", "")
        # Label 1 only if trade hit take-profit
        label = 1 if (outcome == "win" and exit_reason == "tp") else 0
        X_rows.append(vec)
        y_rows.append(label)

    if not X_rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float32), np.empty(0, dtype=np.int32)

    return np.vstack(X_rows), np.array(y_rows, dtype=np.int32)


def rule_based_confidence(indicators: Dict[str, Any], vix: float,
                           direction: str) -> float:
    """
    Cold-start confidence score: weighted sum of indicator alignment.
    Used until 50 trades are logged.

    Score range: 0.0 – 1.0
    """
    score = 0.0
    weights_total = 0.0

    # RSI alignment (weight 0.30)
    rsi = indicators.get("rsi", 50.0)
    if direction == "call":
        rsi_score = max(0.0, (40.0 - rsi) / 40.0)  # lower RSI = better for calls
    else:
        rsi_score = max(0.0, (rsi - 60.0) / 40.0)  # higher RSI = better for puts
    score += rsi_score * 0.30
    weights_total += 0.30

    # MACD crossover (weight 0.25)
    crossover = indicators.get("macd_crossover", "neutral")
    if (direction == "call" and crossover == "bullish") or \
       (direction == "put" and crossover == "bearish"):
        macd_score = 1.0
    elif crossover == "neutral":
        macd_score = 0.3
    else:
        macd_score = 0.0
    score += macd_score * 0.25
    weights_total += 0.25

    # Volume spike (weight 0.20)
    vol_ratio = indicators.get("volume_ratio", 1.0)
    vol_score = min(1.0, (vol_ratio - 1.0) / 1.5)  # 2.5x avg → 1.0
    score += max(0.0, vol_score) * 0.20
    weights_total += 0.20

    # S/R zone quality (weight 0.15)
    zone_quality = indicators.get("sr_zone_quality", 0.0)
    zone_score = min(1.0, zone_quality / 5.0)
    score += zone_score * 0.15
    weights_total += 0.15

    # VIX penalty (weight 0.10)
    vix_val = vix if vix is not None else 15.0
    vix_score = max(0.0, 1.0 - (vix_val - 10.0) / 20.0)  # VIX 10=1.0, VIX 30=0.0
    score += vix_score * 0.10
    weights_total += 0.10

    return round(score / weights_total if weights_total > 0 else 0.0, 4)
