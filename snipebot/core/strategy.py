"""
strategy.py — SMC-based entry and exit decision logic.

Entry requires ALL conditions simultaneously:
  1. Weekly bias aligns with direction (macro top-down filter)
  2. Daily market structure confirmed (trend or CHOCH reversal)
  3. Liquidity sweep completed (on 1H bars)
  4. Price inside Fibonacci 0.618–0.786 retracement zone (daily swing)
  5. Price at / inside an unmitigated daily order block
  6. RVOL >= minimum threshold (1H bars)
  7. ATR expanding (1H bars)
  8. Session is medium or high activity
  9. AI confidence >= threshold
 10. No earnings within buffer days
 11. VIX below maximum
 12. Not in last 15 min of trading day

Output signal includes: entry price, stop-loss, take-profit, confidence.
"""

import logging
import os
from datetime import datetime, time as dt_time, timezone
from typing import Dict, Any, Optional

import pytz
import yaml

from data import database as db
from data.market_data import fetch_vix, earnings_within_days

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_ET       = pytz.timezone("US/Eastern")
_HALT_FILE = os.path.join(_BASE_DIR, "HALT.txt")


def _load_config() -> Dict:
    with open(os.path.join(_BASE_DIR, "config.yaml")) as f:
        return yaml.safe_load(f)


def _get_param(name: str, fallback: float) -> float:
    val = db.get_strategy_param(name)
    return val if val is not None else fallback


def halt_file_exists() -> bool:
    return os.path.exists(_HALT_FILE)


def _is_within_last_15_min() -> bool:
    return datetime.now(_ET).time() >= dt_time(15, 45)


# ── Direction Detection ───────────────────────────────────────────────────────

def detect_direction(indicators: Dict[str, Any]) -> Optional[str]:
    """
    Infer trade direction from market structure and liquidity sweep.

    Returns 'call', 'put', or None if ambiguous.
    """
    # Prioritise the direction already inferred inside compute_all_indicators
    direction = indicators.get("inferred_direction")
    if direction in ("call", "put"):
        return direction

    # Fallback: derive from structure alone
    trend      = indicators.get("market_structure", "ranging")
    sweep_type = indicators.get("sweep_type")
    choch      = indicators.get("choch", False)
    struct_dir = indicators.get("structure_direction")

    if choch and struct_dir == "bullish":
        return "call"
    if choch and struct_dir == "bearish":
        return "put"
    if trend == "uptrend" and sweep_type == "sell_side":
        return "call"
    if trend == "downtrend" and sweep_type == "buy_side":
        return "put"

    return None


# ── Entry Gate ────────────────────────────────────────────────────────────────

def evaluate_conditions(indicators: Dict[str, Any],
                         vix: float,
                         confidence: float,
                         direction: str,
                         ticker: str) -> Dict[str, bool]:
    """
    Evaluate all 12 SMC entry conditions and return a per-condition dict.

    Keys match the signal_candidates table columns (minus the 'cond_' prefix).
    Use this whenever you need individual pass/fail visibility (scanner, near-miss
    tracking).  Call all_entry_conditions_met() when you only need the final bool.
    """
    cfg = _load_config()
    st  = cfg["strategy"]

    # 1. Weekly macro bias
    weekly_trend = indicators.get("weekly_trend", "ranging")
    weekly_bias = (
        (direction == "call" and weekly_trend == "uptrend") or
        (direction == "put"  and weekly_trend == "downtrend")
    )

    # 2. Daily market structure defined (trend or CHOCH)
    trend = indicators.get("market_structure", "ranging")
    daily_structure = trend != "ranging" or bool(indicators.get("choch", False))

    # 3. Liquidity sweep completed
    liquidity_sweep = bool(indicators.get("liquidity_swept", False))

    # 4. Price in Fibonacci 0.618–0.786 zone
    fibonacci_zone = bool(indicators.get("in_fib_zone", False))

    # 5. Price at / inside an order block
    order_block = indicators.get("order_block_quality", 0.0) > 0

    # 6. Relative volume
    rvol_min = _get_param("rvol_min", st.get("rvol_min", 1.5))
    rvol = indicators.get("rvol", 0.0) >= rvol_min

    # 7. ATR expansion
    atr_min = _get_param("atr_expansion_min", st.get("atr_expansion_min", 1.1))
    atr_expansion = indicators.get("atr_expansion_ratio", 1.0) >= atr_min

    # 8. Session timing
    session_min = int(_get_param("session_score_min", st.get("session_score_min", 1)))
    session_score = indicators.get("session_score", 0) >= session_min

    # 9. AI confidence
    conf_min = _get_param("ai_confidence_min", st.get("ai_confidence_min", 0.72))
    ai_confidence = confidence >= conf_min

    # 10. Earnings buffer
    buffer = int(_get_param("earnings_buffer_days", st.get("earnings_buffer_days", 5)))
    earnings_clear = not earnings_within_days(ticker, buffer)

    # 11. VIX below max
    vix_max = _get_param("vix_max", st.get("vix_max", 30))
    vix_ok = vix is None or vix < vix_max

    # 12. Not in last 15 min of trading day
    not_eod = not _is_within_last_15_min()

    return {
        "weekly_bias":     weekly_bias,
        "daily_structure": daily_structure,
        "liquidity_sweep": liquidity_sweep,
        "fibonacci_zone":  fibonacci_zone,
        "order_block":     order_block,
        "rvol":            rvol,
        "atr_expansion":   atr_expansion,
        "session_score":   session_score,
        "ai_confidence":   ai_confidence,
        "earnings_clear":  earnings_clear,
        "vix_ok":          vix_ok,
        "not_eod":         not_eod,
    }


def all_entry_conditions_met(indicators: Dict[str, Any],
                               vix: float,
                               confidence: float,
                               direction: str,
                               ticker: str) -> bool:
    """Return True only when every SMC entry condition passes."""
    if halt_file_exists():
        logger.debug("HALT file present")
        return False
    results = evaluate_conditions(indicators, vix, confidence, direction, ticker)
    if not all(results.values()):
        failed = [k for k, v in results.items() if not v]
        logger.debug("%s: failed conditions: %s", ticker, failed)
        return False
    return True


# ── Signal Builder ────────────────────────────────────────────────────────────

def build_signal(ticker: str,
                 indicators: Dict[str, Any],
                 confidence: float,
                 vix: float,
                 direction: str) -> Dict[str, Any]:
    """
    Assemble the full trade signal dict.

    Includes entry price, stop-loss, and take-profit derived from order block
    and ATR so the executor and Discord message have precise levels.
    """
    cfg = _load_config()
    st  = cfg["strategy"]
    now = datetime.now(timezone.utc)

    current_price = indicators["current_price"]
    atr           = indicators.get("atr", current_price * 0.01)
    nearest_ob    = indicators.get("nearest_ob") or {}
    fib           = indicators.get("fib") or {}

    # Stop-loss: just below/above the order block (+ 0.5 ATR buffer)
    if direction == "call":
        sl_price = round((nearest_ob.get("low", current_price) - 0.5 * atr), 4)
    else:
        sl_price = round((nearest_ob.get("high", current_price) + 0.5 * atr), 4)

    # Take-profit: toward the swing high/low (minimum 2:1 R:R)
    sl_dist = abs(current_price - sl_price)
    if direction == "call":
        tp_price = round(current_price + max(sl_dist * 2, atr * 3), 4)
    else:
        tp_price = round(current_price - max(sl_dist * 2, atr * 3), 4)

    return {
        "ticker":             ticker,
        "direction":          direction,
        "signal_time":        now.isoformat(),
        "current_price":      current_price,
        # SMC context
        "market_structure":   indicators.get("market_structure"),
        "choch":              indicators.get("choch", False),
        "sweep_type":         indicators.get("sweep_type"),
        "sweep_level":        indicators.get("sweep_level"),
        "fib_zone_low":       fib.get("zone_low"),
        "fib_zone_high":      fib.get("zone_high"),
        "ob_high":            nearest_ob.get("high"),
        "ob_low":             nearest_ob.get("low"),
        "ob_quality":         indicators.get("order_block_quality", 0.0),
        # Metrics
        "rvol":               indicators.get("rvol"),
        "atr":                atr,
        "atr_expansion_ratio": indicators.get("atr_expansion_ratio"),
        "session_score":      indicators.get("session_score"),
        "vix":                vix,
        "ai_confidence":      confidence,
        # Levels
        "entry_price":        current_price,
        "sl_price":           sl_price,
        "tp_price":           tp_price,
        # Filled by scanner after options chain lookup
        "option_symbol":      None,
        "strike":             None,
        "expiry":             None,
        "dte":                None,
        "premium":            None,
        "qty":                None,
        "total_cost":         None,
    }


# ── Trade Record Builder ──────────────────────────────────────────────────────

def signal_to_trade_record(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an approved signal into a DB insert record."""
    from datetime import date
    return {
        "ticker":          signal["ticker"],
        "direction":       signal["direction"],
        "entry_price":     signal.get("premium"),
        "exit_price":      None,
        "entry_date":      date.today().isoformat(),
        "exit_date":       None,
        "pnl":             None,
        "pnl_pct":         None,
        "exit_reason":     None,
        "rsi_at_entry":    None,                           # not used in SMC strategy
        "macd_signal":     signal.get("sweep_type"),       # repurposed field
        "volume_ratio":    signal.get("rvol"),
        "sr_zone_quality": signal.get("ob_quality"),
        "vix_at_entry":    signal.get("vix"),
        "ai_confidence":   signal.get("ai_confidence"),
        "market_regime":   signal.get("market_structure"),
        "outcome":         None,
    }
