"""
indicators.py — Technical indicators and S/R zone detection.

Provides: RSI, MACD, volume ratio, and fractal pivot + K-means S/R zones.
All functions accept a pandas DataFrame with lowercase OHLCV columns.
"""

import logging
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)

# ── RSI ───────────────────────────────────────────────────────────────────────

def compute_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Return the most-recent RSI value (0–100)."""
    close = df["close"].astype(float)
    if len(close) < period + 1:
        logger.warning("Not enough bars for RSI (need %d, got %d)", period + 1, len(close))
        return 50.0  # neutral fallback

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return float(rsi_series.iloc[-1])


# ── MACD ─────────────────────────────────────────────────────────────────────

def compute_macd(df: pd.DataFrame,
                 fast: int = 12, slow: int = 26,
                 signal: int = 9) -> Dict[str, float]:
    """
    Return dict with keys: macd, signal, histogram, crossover_signal.
    crossover_signal: 'bullish', 'bearish', or 'neutral'.
    """
    close = df["close"].astype(float)
    if len(close) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0, "crossover_signal": "neutral"}

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    prev_hist = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0.0
    curr_hist = float(histogram.iloc[-1])

    if prev_hist < 0 and curr_hist >= 0:
        crossover = "bullish"
    elif prev_hist > 0 and curr_hist <= 0:
        crossover = "bearish"
    else:
        crossover = "neutral"

    return {
        "macd": round(float(macd_line.iloc[-1]), 6),
        "signal": round(float(signal_line.iloc[-1]), 6),
        "histogram": round(curr_hist, 6),
        "crossover_signal": crossover,
    }


# ── Volume Ratio ──────────────────────────────────────────────────────────────

def compute_volume_ratio(df: pd.DataFrame, avg_period: int = 20) -> float:
    """Return current-bar volume / 20-day average volume."""
    volume = df["volume"].astype(float)
    if len(volume) < avg_period + 1:
        return 1.0  # neutral fallback
    avg_vol = volume.iloc[-avg_period - 1:-1].mean()
    if avg_vol == 0:
        return 1.0
    return round(float(volume.iloc[-1]) / avg_vol, 4)


# ── Market Regime ─────────────────────────────────────────────────────────────

def detect_market_regime(df: pd.DataFrame) -> str:
    """
    Classify the recent market as 'trending', 'ranging', or 'volatile'.
    Uses ADX for trending detection, ATR/price ratio for volatility.
    """
    if len(df) < 30:
        return "ranging"

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    # ATR-based volatility
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = atr / close.iloc[-1]

    if atr_pct > 0.03:
        return "volatile"

    # Simple trend detection: price above/below 20-period SMA
    sma20 = close.rolling(20).mean()
    slope = (sma20.iloc[-1] - sma20.iloc[-10]) / sma20.iloc[-10]

    if abs(slope) > 0.01:
        return "trending"
    return "ranging"


# ── Support / Resistance Zones ────────────────────────────────────────────────

def detect_support_resistance(df: pd.DataFrame,
                               n_zones: int = 5,
                               order: int = 3) -> List[Dict]:
    """
    Detect S/R zones using fractal pivot points + K-means clustering.

    Parameters
    ----------
    df     : Daily OHLCV DataFrame (30-day lookback recommended)
    n_zones: Number of zone clusters to return
    order  : Argrelextrema neighbourhood order for pivot detection

    Returns
    -------
    List of dicts with keys: low, high, center, touches, quality
    """
    if len(df) < order * 2 + 1:
        return []

    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    close = df["close"].astype(float).values
    n = len(close)

    # Fractal pivot highs and lows
    pivot_highs_idx = argrelextrema(high, np.greater, order=order)[0]
    pivot_lows_idx = argrelextrema(low, np.less, order=order)[0]

    pivot_prices = np.concatenate([high[pivot_highs_idx], low[pivot_lows_idx]])
    pivot_ages = np.concatenate([pivot_highs_idx, pivot_lows_idx])  # index = age proxy

    if len(pivot_prices) < 2:
        return []

    # K-means clustering on pivot prices
    from scipy.cluster.vq import kmeans, vq
    n_clusters = min(n_zones, len(pivot_prices))
    try:
        centroids, _ = kmeans(pivot_prices, n_clusters, iter=20)
    except Exception:
        return []

    labels, _ = vq(pivot_prices, centroids)

    zones = []
    for idx in range(n_clusters):
        mask = labels == idx
        cluster_prices = pivot_prices[mask]
        cluster_ages = pivot_ages[mask]

        center = float(centroids[idx])
        zone_range = cluster_prices.std() if len(cluster_prices) > 1 else center * 0.002
        zone_low = center - zone_range
        zone_high = center + zone_range
        touches = int(mask.sum())

        # Recency weight: more recent pivots score higher
        recency_scores = cluster_ages / n  # 0=oldest, 1=newest
        recency_weight = float(recency_scores.mean())

        quality = touches * (0.5 + 0.5 * recency_weight)

        zones.append({
            "low": round(zone_low, 4),
            "high": round(zone_high, 4),
            "center": round(center, 4),
            "touches": touches,
            "quality": round(quality, 4),
        })

    # Sort by quality descending
    zones.sort(key=lambda z: z["quality"], reverse=True)
    return zones


def price_in_zone(price: float, zone: Dict, tolerance: float = 0.003) -> bool:
    """
    Return True if *price* is within *zone* (expanded by ±tolerance fraction).
    """
    low = zone["low"] * (1 - tolerance)
    high = zone["high"] * (1 + tolerance)
    return low <= price <= high


def nearest_zone_distance(price: float, zones: List[Dict]) -> Tuple[Optional[Dict], float]:
    """
    Return (nearest_zone, distance_pct) where distance_pct is |price-center|/price.
    Returns (None, 1.0) if zones is empty.
    """
    if not zones:
        return None, 1.0
    best_zone = min(zones, key=lambda z: abs(price - z["center"]))
    dist_pct = abs(price - best_zone["center"]) / price
    return best_zone, round(dist_pct, 6)


# ── Composite Indicator Bundle ────────────────────────────────────────────────

def compute_all_indicators(df: pd.DataFrame,
                            sr_zones: List[Dict]) -> Dict:
    """
    Compute RSI, MACD, volume ratio, regime, and S/R proximity in one call.
    Returns a flat dict for consumption by strategy.py and feature_engineer.py.
    """
    current_price = float(df["close"].iloc[-1])
    rsi = compute_rsi(df)
    macd = compute_macd(df)
    vol_ratio = compute_volume_ratio(df)
    regime = detect_market_regime(df)
    nearest_zone, dist_pct = nearest_zone_distance(current_price, sr_zones)

    in_zone = False
    zone_quality = 0.0
    if nearest_zone:
        in_zone = price_in_zone(current_price, nearest_zone)
        zone_quality = nearest_zone["quality"] if in_zone else 0.0

    return {
        "current_price": current_price,
        "rsi": round(rsi, 4),
        "macd_histogram": macd["histogram"],
        "macd_crossover": macd["crossover_signal"],
        "volume_ratio": vol_ratio,
        "market_regime": regime,
        "in_sr_zone": in_zone,
        "nearest_zone": nearest_zone,
        "sr_zone_distance_pct": dist_pct,
        "sr_zone_quality": zone_quality,
    }
