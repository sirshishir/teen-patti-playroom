"""
indicators.py — Smart Money Concepts (SMC) technical analysis engine.

Multi-timeframe stack (appropriate for 14–30 DTE options):
  Weekly  → detect_weekly_bias()          macro trend direction
  Daily   → detect_market_structure()     BOS/CHOCH, order blocks, Fib, liquidity
  4-Hour  → check_4h_ob_confluence()      intermediate OB confirmation
  1-Hour  → compute_all_indicators()      entry trigger: sweep, RVOL, ATR, session
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)

_ET = pytz.timezone("US/Eastern")


# ── Swing Point Detection ─────────────────────────────────────────────────────

def detect_swing_points(df: pd.DataFrame,
                         order: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return indices of significant swing highs and swing lows.

    Parameters
    ----------
    df    : OHLCV DataFrame
    order : neighbourhood half-width for argrelextrema

    Returns
    -------
    (swing_high_indices, swing_low_indices)
    """
    high = df["high"].astype(float).values
    low  = df["low"].astype(float).values

    sh_idx = argrelextrema(high, np.greater_equal, order=order)[0]
    sl_idx = argrelextrema(low,  np.less_equal,    order=order)[0]

    # Deduplicate consecutive equal extrema
    sh_idx = _dedupe_extrema(high, sh_idx, mode="high")
    sl_idx = _dedupe_extrema(low,  sl_idx, mode="low")

    return sh_idx, sl_idx


def _dedupe_extrema(arr: np.ndarray, idx: np.ndarray, mode: str) -> np.ndarray:
    """Keep only the most extreme value when consecutive indices are equal."""
    if len(idx) == 0:
        return idx
    keep = []
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] - idx[j] <= 1:
            j += 1
        group = idx[i:j + 1]
        if mode == "high":
            keep.append(group[np.argmax(arr[group])])
        else:
            keep.append(group[np.argmin(arr[group])])
        i = j + 1
    return np.array(keep)


# ── Market Structure ──────────────────────────────────────────────────────────

def detect_market_structure(df: pd.DataFrame,
                              sh_idx: np.ndarray,
                              sl_idx: np.ndarray) -> Dict:
    """
    Classify trend and detect BOS / CHOCH from swing point sequences.

    Returns dict with keys:
      trend           : 'uptrend' | 'downtrend' | 'ranging'
      bos             : bool — Break of Structure occurred recently
      choch           : bool — Change of Character occurred recently
      structure_direction : 'bullish' | 'bearish' | None  (direction of latest BOS/CHOCH)
      last_sh         : float — most recent swing high price
      last_sl         : float — most recent swing low price
      last_sh_idx     : int
      last_sl_idx     : int
    """
    high  = df["high"].astype(float).values
    low   = df["low"].astype(float).values
    close = df["close"].astype(float).values
    n     = len(close)

    default = {
        "trend": "ranging", "bos": False, "choch": False,
        "structure_direction": None,
        "last_sh": float(high[-1]), "last_sl": float(low[-1]),
        "last_sh_idx": int(sh_idx[-1]) if len(sh_idx) else n - 1,
        "last_sl_idx": int(sl_idx[-1]) if len(sl_idx) else n - 1,
    }

    if len(sh_idx) < 2 or len(sl_idx) < 2:
        return default

    # Build ordered pivot sequence (alternating highs / lows by index)
    pivots = []
    for i in sh_idx:
        pivots.append(("H", i, high[i]))
    for i in sl_idx:
        pivots.append(("L", i, low[i]))
    pivots.sort(key=lambda x: x[1])

    # Collapse consecutive same-type pivots (keep extreme)
    merged = []
    for p in pivots:
        if merged and merged[-1][0] == p[0]:
            if p[0] == "H" and p[2] > merged[-1][2]:
                merged[-1] = p
            elif p[0] == "L" and p[2] < merged[-1][2]:
                merged[-1] = p
        else:
            merged.append(list(p))

    if len(merged) < 4:
        return default

    # Use last 6 pivots for structure analysis
    recent = merged[-6:]
    highs = [p for p in recent if p[0] == "H"]
    lows  = [p for p in recent if p[0] == "L"]

    if len(highs) < 2 or len(lows) < 2:
        return default

    hh = highs[-1][2] > highs[-2][2]   # higher high
    hl = lows[-1][2]  > lows[-2][2]    # higher low
    lh = highs[-1][2] < highs[-2][2]   # lower high
    ll = lows[-1][2]  < lows[-2][2]    # lower low

    if hh and hl:
        trend = "uptrend"
    elif lh and ll:
        trend = "downtrend"
    else:
        trend = "ranging"

    # BOS / CHOCH — check if last close broke a key level
    last_close    = close[-1]
    prev_sh_price = highs[-2][2]
    prev_sl_price = lows[-2][2]

    bos   = False
    choch = False
    struct_dir: Optional[str] = None

    if trend == "uptrend" and last_close > prev_sh_price:
        bos = True
        struct_dir = "bullish"
    elif trend == "downtrend" and last_close < prev_sl_price:
        bos = True
        struct_dir = "bearish"
    elif trend == "downtrend" and last_close > prev_sh_price:
        choch = True
        struct_dir = "bullish"
    elif trend == "uptrend" and last_close < prev_sl_price:
        choch = True
        struct_dir = "bearish"

    return {
        "trend": trend,
        "bos": bos,
        "choch": choch,
        "structure_direction": struct_dir,
        "last_sh": float(highs[-1][2]),
        "last_sl": float(lows[-1][2]),
        "last_sh_idx": int(highs[-1][1]),
        "last_sl_idx": int(lows[-1][1]),
    }


# ── Liquidity Zones ───────────────────────────────────────────────────────────

def detect_liquidity_zones(df: pd.DataFrame,
                            tolerance: float = 0.002) -> List[Dict]:
    """
    Find equal highs (buy-side liquidity) and equal lows (sell-side liquidity).

    Returns list of dicts:
      type  : 'buy_side' | 'sell_side'
      level : float — price of the liquidity pool
      count : int   — number of touches
    """
    high  = df["high"].astype(float).values
    low   = df["low"].astype(float).values
    zones = []

    # Scan for equal highs
    for i in range(len(high)):
        matches = [h for h in high[max(0, i-30):i] if abs(h - high[i]) / high[i] <= tolerance]
        if len(matches) >= 1:
            zones.append({
                "type": "buy_side",
                "level": round(float(high[i]), 4),
                "count": len(matches) + 1,
            })

    # Scan for equal lows
    for i in range(len(low)):
        matches = [l for l in low[max(0, i-30):i] if abs(l - low[i]) / low[i] <= tolerance]
        if len(matches) >= 1:
            zones.append({
                "type": "sell_side",
                "level": round(float(low[i]), 4),
                "count": len(matches) + 1,
            })

    # Deduplicate nearby zones of same type
    return _merge_nearby_zones(zones, tolerance)


def _merge_nearby_zones(zones: List[Dict], tolerance: float) -> List[Dict]:
    merged = []
    for z in sorted(zones, key=lambda x: x["level"]):
        absorbed = False
        for m in merged:
            if m["type"] == z["type"] and abs(m["level"] - z["level"]) / m["level"] <= tolerance:
                m["level"] = (m["level"] * m["count"] + z["level"] * z["count"]) / (m["count"] + z["count"])
                m["count"] += z["count"]
                absorbed = True
                break
        if not absorbed:
            merged.append(dict(z))
    return merged


# ── Liquidity Sweep ───────────────────────────────────────────────────────────

def detect_liquidity_sweep(df: pd.DataFrame,
                            liquidity_zones: List[Dict],
                            lookback: int = 10) -> Dict:
    """
    Detect if price recently swept a liquidity zone and closed back inside.

    A sweep = wick pierces zone level, candle body closes on opposite side.

    Returns dict:
      swept       : bool
      sweep_type  : 'buy_side' | 'sell_side' | None
      sweep_level : float | None
    """
    if not liquidity_zones or len(df) < lookback + 1:
        return {"swept": False, "sweep_type": None, "sweep_level": None}

    recent = df.iloc[-lookback:]
    highs  = recent["high"].astype(float).values
    lows   = recent["low"].astype(float).values
    closes = recent["close"].astype(float).values

    for zone in liquidity_zones:
        lvl  = zone["level"]
        ztype = zone["type"]

        for i in range(len(recent)):
            if ztype == "buy_side":
                # Wick above level, close below → bearish sweep (PUT signal)
                if highs[i] > lvl and closes[i] < lvl:
                    return {"swept": True, "sweep_type": "buy_side", "sweep_level": lvl}
            elif ztype == "sell_side":
                # Wick below level, close above → bullish sweep (CALL signal)
                if lows[i] < lvl and closes[i] > lvl:
                    return {"swept": True, "sweep_type": "sell_side", "sweep_level": lvl}

    return {"swept": False, "sweep_type": None, "sweep_level": None}


# ── Order Block Detection ─────────────────────────────────────────────────────

def detect_order_blocks(df: pd.DataFrame,
                         sh_idx: np.ndarray,
                         sl_idx: np.ndarray,
                         atr: float) -> List[Dict]:
    """
    Identify bullish and bearish order blocks (last opposing candle before impulse).

    Bullish OB : last bearish candle before a bullish impulse (≥ 1.5 × ATR in 3 bars)
    Bearish OB : last bullish candle before a bearish impulse (≥ 1.5 × ATR in 3 bars)

    Returns list of dicts:
      type      : 'bullish' | 'bearish'
      high      : float
      low       : float
      center    : float
      strength  : float (impulse size / ATR)
      index     : int (bar index in df)
      mitigated : bool (price has since traded through the OB)
    """
    opens  = df["open"].astype(float).values
    highs  = df["high"].astype(float).values
    lows   = df["low"].astype(float).values
    closes = df["close"].astype(float).values
    n      = len(closes)
    impulse_min = 1.5 * atr if atr > 0 else 0.001

    obs = []
    for i in range(n - 4):
        # Bullish OB: bearish candle at i, followed by bullish impulse
        if closes[i] < opens[i]:  # bearish candle
            future_move = max(closes[i+1:i+4]) - closes[i]
            if future_move >= impulse_min:
                ob_high = max(opens[i], closes[i])
                ob_low  = min(opens[i], closes[i])
                mitigated = any(lows[j] < ob_low for j in range(i + 1, n))
                strength = round(future_move / atr, 2) if atr > 0 else 1.0
                obs.append({
                    "type": "bullish", "high": round(ob_high, 4),
                    "low": round(ob_low, 4),
                    "center": round((ob_high + ob_low) / 2, 4),
                    "strength": strength, "index": i,
                    "mitigated": mitigated,
                })

        # Bearish OB: bullish candle at i, followed by bearish impulse
        if closes[i] > opens[i]:  # bullish candle
            future_move = closes[i] - min(closes[i+1:i+4])
            if future_move >= impulse_min:
                ob_high = max(opens[i], closes[i])
                ob_low  = min(opens[i], closes[i])
                mitigated = any(highs[j] > ob_high for j in range(i + 1, n))
                strength = round(future_move / atr, 2) if atr > 0 else 1.0
                obs.append({
                    "type": "bearish", "high": round(ob_high, 4),
                    "low": round(ob_low, 4),
                    "center": round((ob_high + ob_low) / 2, 4),
                    "strength": strength, "index": i,
                    "mitigated": mitigated,
                })

    # Keep only unmitigated blocks, sort by recency (index desc)
    obs = [o for o in obs if not o["mitigated"]]
    obs.sort(key=lambda x: x["index"], reverse=True)
    return obs[:10]  # cap to most recent 10


def nearest_order_block(price: float,
                         order_blocks: List[Dict],
                         direction: str,
                         tolerance: float = 0.003) -> Tuple[Optional[Dict], float, float]:
    """
    Return (best_ob, quality_score, distance_pct) for the given direction.

    For calls : look for unmitigated BULLISH OB below current price
    For puts  : look for unmitigated BEARISH OB above current price

    distance_pct : |price - ob_center| / price
    quality      : ob.strength (higher = better)
    """
    ob_type = "bullish" if direction == "call" else "bearish"
    candidates = [ob for ob in order_blocks if ob["type"] == ob_type]

    if not candidates:
        return None, 0.0, 1.0

    # Filter to OBs where price is near or inside
    relevant = []
    for ob in candidates:
        expanded_low  = ob["low"]  * (1 - tolerance)
        expanded_high = ob["high"] * (1 + tolerance)
        if ob_type == "bullish":
            if expanded_low <= price <= expanded_high or price >= ob["low"]:
                relevant.append(ob)
        else:
            if expanded_low <= price <= expanded_high or price <= ob["high"]:
                relevant.append(ob)

    if not relevant:
        # Return closest even if outside tolerance
        relevant = candidates

    best = min(relevant, key=lambda ob: abs(price - ob["center"]))
    dist_pct = abs(price - best["center"]) / price

    # Price is "in" the OB if within tolerance
    in_ob = dist_pct <= tolerance or (best["low"] <= price <= best["high"])
    quality = best["strength"] if in_ob else 0.0

    return best, round(quality, 4), round(dist_pct, 6)


# ── Fibonacci Retracement ─────────────────────────────────────────────────────

def compute_fibonacci_levels(df: pd.DataFrame,
                              sh_idx: np.ndarray,
                              sl_idx: np.ndarray,
                              market_structure: Dict) -> Dict:
    """
    Auto-detect the current swing and compute Fibonacci retracement levels.

    For uptrend  : swing from most recent SL → most recent SH (retracement down)
    For downtrend: swing from most recent SH → most recent SL (retracement up)

    Returns dict:
      swing_high, swing_low, range, levels (dict of ratio→price),
      zone_low (0.618 level), zone_high (0.786 level), trend_direction
    """
    high   = df["high"].astype(float).values
    low    = df["low"].astype(float).values
    trend  = market_structure.get("trend", "ranging")
    empty  = {"swing_high": None, "swing_low": None, "range": 0,
               "levels": {}, "zone_low": None, "zone_high": None,
               "trend_direction": trend}

    if len(sh_idx) == 0 or len(sl_idx) == 0:
        return empty

    if trend == "uptrend":
        swing_high = float(high[sh_idx[-1]])
        # Find most recent SL that precedes the latest SH
        prior_sl = [i for i in sl_idx if i < sh_idx[-1]]
        if not prior_sl:
            return empty
        swing_low = float(low[prior_sl[-1]])
        direction = "bullish"
    elif trend == "downtrend":
        swing_low = float(low[sl_idx[-1]])
        prior_sh = [i for i in sh_idx if i < sl_idx[-1]]
        if not prior_sh:
            return empty
        swing_high = float(high[prior_sh[-1]])
        direction = "bearish"
    else:
        # Ranging: use overall range
        swing_high = float(high[sh_idx[-1]])
        swing_low  = float(low[sl_idx[-1]])
        direction  = "neutral"

    price_range = swing_high - swing_low
    if price_range <= 0:
        return empty

    # Standard Fibonacci levels (retracement from swing_high toward swing_low)
    ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    levels = {r: round(swing_high - r * price_range, 4) for r in ratios}

    # High-probability entry zone
    zone_high = levels[0.618]  # higher price (shallower retracement)
    zone_low  = levels[0.786]  # lower price  (deeper retracement)

    return {
        "swing_high": round(swing_high, 4),
        "swing_low":  round(swing_low,  4),
        "range": round(price_range, 4),
        "levels": levels,
        "zone_low":  round(zone_low,  4),
        "zone_high": round(zone_high, 4),
        "trend_direction": direction,
    }


def price_in_fib_zone(price: float, fib: Dict,
                       direction: str,
                       fib_min: float = 0.618,
                       fib_max: float = 0.786) -> bool:
    """
    Return True if *price* is inside the Fibonacci retracement zone.

    For calls (uptrend retracement): price must be between zone_low and zone_high.
    For puts  (downtrend retracement): same logic mirrored.
    """
    zone_low  = fib.get("zone_low")
    zone_high = fib.get("zone_high")
    if zone_low is None or zone_high is None:
        return False

    lo = min(zone_low, zone_high)
    hi = max(zone_low, zone_high)
    return lo <= price <= hi


def fib_zone_distance(price: float, fib: Dict) -> float:
    """Return 0.0 if inside zone; fractional distance outside otherwise."""
    if not fib.get("zone_low") or not fib.get("zone_high"):
        return 1.0
    lo = min(fib["zone_low"], fib["zone_high"])
    hi = max(fib["zone_low"], fib["zone_high"])
    if lo <= price <= hi:
        return 0.0
    nearest = lo if price < lo else hi
    return abs(price - nearest) / price


# ── Weekly Bias ───────────────────────────────────────────────────────────────

def detect_weekly_bias(df_weekly: pd.DataFrame) -> Dict:
    """
    Determine macro trend from weekly bars using swing structure + 20-week SMA.

    Both swing structure AND SMA must agree to declare a trend — if they
    conflict the bias is 'ranging' and no trades are taken.

    Returns dict with keys:
      trend      : 'uptrend' | 'downtrend' | 'ranging'
      sma20      : float
      above_sma  : bool
      raw_structure : raw trend from swing analysis (before SMA filter)
    """
    if len(df_weekly) < 10:
        return {"trend": "ranging", "sma20": None,
                "above_sma": None, "raw_structure": "ranging"}

    sh_idx, sl_idx = detect_swing_points(df_weekly, order=2)
    struct         = detect_market_structure(df_weekly, sh_idx, sl_idx)

    close      = df_weekly["close"].astype(float)
    sma_period = min(20, len(close) - 1)
    sma20      = float(close.rolling(sma_period).mean().iloc[-1])
    above_sma  = float(close.iloc[-1]) > sma20
    raw_trend  = struct["trend"]

    if raw_trend == "uptrend" and above_sma:
        final_trend = "uptrend"
    elif raw_trend == "downtrend" and not above_sma:
        final_trend = "downtrend"
    else:
        final_trend = "ranging"   # conflicting signals — sit out

    return {
        "trend":         final_trend,
        "sma20":         round(sma20, 4),
        "above_sma":     above_sma,
        "raw_structure": raw_trend,
    }


# ── 4-Hour OB Confluence ──────────────────────────────────────────────────────

def check_4h_ob_confluence(price: float,
                            ob_4h: List[Dict],
                            direction: str,
                            tolerance: float = 0.005) -> Tuple[bool, float]:
    """
    Return (has_confluence, quality_score) if *price* is inside or near a
    4-hour order block that aligns with *direction*.

    For calls : look for unmitigated bullish 4H OB near current price
    For puts  : look for unmitigated bearish 4H OB near current price

    tolerance : expanded OB boundary (±0.5% default — wider than daily)
    """
    if not ob_4h:
        return False, 0.0

    ob_type    = "bullish" if direction == "call" else "bearish"
    candidates = [ob for ob in ob_4h
                  if ob["type"] == ob_type and not ob.get("mitigated", False)]

    best_quality = 0.0
    for ob in candidates:
        lo = ob["low"]  * (1 - tolerance)
        hi = ob["high"] * (1 + tolerance)
        if lo <= price <= hi:
            best_quality = max(best_quality, ob.get("strength", 1.0))

    return best_quality > 0, round(best_quality, 4)


# ── Relative Volume ───────────────────────────────────────────────────────────

def compute_rvol(df: pd.DataFrame, period: int = 20) -> float:
    """Return current bar volume divided by the rolling mean of prior *period* bars."""
    vol = df["volume"].astype(float)
    if len(vol) < period + 1:
        return 1.0
    avg = vol.iloc[-period - 1:-1].mean()
    if avg == 0:
        return 1.0
    return round(float(vol.iloc[-1]) / avg, 4)


# ── ATR & Volatility Expansion ────────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Return the most recent ATR value."""
    if len(df) < period + 1:
        return float((df["high"] - df["low"]).mean())
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])


def check_atr_expansion(df: pd.DataFrame,
                         fast: int = 14,
                         slow: int = 50) -> Tuple[bool, float]:
    """
    Return (is_expanding, ratio) where ratio = fast_ATR / slow_ATR.
    Expansion is confirmed when ratio > atr_expansion_min (default 1.1).
    """
    if len(df) < slow + 1:
        return False, 1.0
    fast_atr = compute_atr(df, fast)
    slow_atr = compute_atr(df, slow)
    if slow_atr == 0:
        return False, 1.0
    ratio = round(fast_atr / slow_atr, 4)
    return ratio > 1.1, ratio


# ── Session Timing ────────────────────────────────────────────────────────────

def check_session_timing(now: Optional[datetime] = None) -> int:
    """
    Return session activity score for the current ET time.

    2 = High   : London–NY overlap (08:00–11:00 ET), NY afternoon (14:30–15:30 ET)
    1 = Medium : Pre-NY (07:00–08:00), NY morning continuation (11:00–12:00),
                  post-lunch (13:30–14:30)
    0 = Low    : NY lunch (12:00–13:30), pre-market (<07:00), near-close (>15:30)
    """
    if now is None:
        now = datetime.now(_ET)
    elif now.tzinfo is None:
        now = _ET.localize(now)
    else:
        now = now.astimezone(_ET)

    h, m = now.hour, now.minute
    t = h * 60 + m  # minutes since midnight ET

    HIGH_WINDOWS   = [(8*60, 11*60), (14*60+30, 15*60+30)]
    MEDIUM_WINDOWS = [(7*60, 8*60),  (11*60, 12*60), (13*60+30, 14*60+30)]

    for lo, hi in HIGH_WINDOWS:
        if lo <= t < hi:
            return 2
    for lo, hi in MEDIUM_WINDOWS:
        if lo <= t < hi:
            return 1
    return 0


# ── Composite Indicator Bundle ────────────────────────────────────────────────

def compute_all_indicators(df: pd.DataFrame,
                            cached_analysis: Optional[Dict] = None) -> Dict:
    """
    Compute all SMC indicators and return a flat dict for strategy.py and
    feature_engineer.py.

    *cached_analysis* is the daily-data cache built by market_data.cache_sr_zones().
    If not provided, indicators are computed from *df* directly (less accurate
    for market structure).
    """
    current_price = float(df["close"].iloc[-1])

    # ── Pull from daily cache if available ──────────────────────────────────
    if cached_analysis:
        weekly_bias     = cached_analysis.get("weekly_bias", {"trend": "ranging"})
        market_struct   = cached_analysis.get("market_structure", {})
        order_blocks    = cached_analysis.get("order_blocks", [])
        liquidity_zones = cached_analysis.get("liquidity_zones", [])
        fib             = cached_analysis.get("fibonacci", {})
        ob_4h           = cached_analysis.get("ob_4h", [])
    else:
        weekly_bias    = {"trend": "ranging"}
        sh_idx, sl_idx = detect_swing_points(df, order=3)
        market_struct  = detect_market_structure(df, sh_idx, sl_idx)
        liquidity_zones = detect_liquidity_zones(df)
        atr_val_d      = compute_atr(df)
        order_blocks   = detect_order_blocks(df, sh_idx, sl_idx, atr_val_d)
        fib            = compute_fibonacci_levels(df, sh_idx, sl_idx, market_struct)
        ob_4h          = []

    # ── Intraday indicators from 5-min df ────────────────────────────────────
    rvol             = compute_rvol(df)
    atr_val          = compute_atr(df)
    atr_expanding, atr_ratio = check_atr_expansion(df)
    session_score    = check_session_timing()

    # ── Liquidity sweep on recent intraday bars ──────────────────────────────
    sweep = detect_liquidity_sweep(df, liquidity_zones, lookback=12)

    # ── Infer direction from structure + sweep ───────────────────────────────
    trend  = market_struct.get("trend", "ranging")
    choch  = market_struct.get("choch", False)
    struct_dir = market_struct.get("structure_direction")

    if choch and struct_dir == "bullish":
        inferred_direction = "call"
    elif choch and struct_dir == "bearish":
        inferred_direction = "put"
    elif trend == "uptrend" and sweep.get("sweep_type") == "sell_side":
        inferred_direction = "call"
    elif trend == "downtrend" and sweep.get("sweep_type") == "buy_side":
        inferred_direction = "put"
    else:
        inferred_direction = None

    # ── Direction-dependent checks ───────────────────────────────────────────
    in_fib_zone     = False
    fib_dist        = 1.0
    nearest_ob      = None
    ob_quality      = 0.0
    ob_dist         = 1.0
    has_4h_conf     = False
    ob_4h_quality   = 0.0

    if inferred_direction and fib:
        in_fib_zone = price_in_fib_zone(current_price, fib, inferred_direction)
        fib_dist    = fib_zone_distance(current_price, fib)
        nearest_ob, ob_quality, ob_dist = nearest_order_block(
            current_price, order_blocks, inferred_direction
        )
        has_4h_conf, ob_4h_quality = check_4h_ob_confluence(
            current_price, ob_4h, inferred_direction
        )

    return {
        "current_price":        current_price,
        # Weekly macro bias
        "weekly_bias":          weekly_bias,
        "weekly_trend":         weekly_bias.get("trend", "ranging"),
        # Daily market structure
        "market_structure":     trend,
        "bos":                  market_struct.get("bos", False),
        "choch":                choch,
        "structure_direction":  struct_dir,
        "last_sh":              market_struct.get("last_sh"),
        "last_sl":              market_struct.get("last_sl"),
        # Liquidity (checked on 1H bars)
        "liquidity_zones":      liquidity_zones,
        "liquidity_swept":      sweep.get("swept", False),
        "sweep_type":           sweep.get("sweep_type"),
        "sweep_level":          sweep.get("sweep_level"),
        # Fibonacci (daily swing)
        "fib":                  fib,
        "in_fib_zone":          in_fib_zone,
        "fib_zone_distance":    fib_dist,
        # Daily order blocks
        "order_blocks":         order_blocks,
        "nearest_ob":           nearest_ob,
        "order_block_quality":  ob_quality,
        "ob_distance_pct":      ob_dist,
        # 4-Hour OB confluence
        "has_4h_ob_confluence": has_4h_conf,
        "ob_4h_quality":        ob_4h_quality,
        # Volume & volatility (1H bars)
        "rvol":                 rvol,
        "atr":                  round(atr_val, 6),
        "atr_expanding":        atr_expanding,
        "atr_expansion_ratio":  atr_ratio,
        # Session timing
        "session_score":        session_score,
        # Inferred direction
        "inferred_direction":   inferred_direction,
    }
