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

def evaluate_conditions_detailed(indicators: Dict[str, Any],
                                 vix: float,
                                 confidence: float,
                                 direction: str,
                                 ticker: str) -> Dict[str, tuple]:
    """
    Evaluate all 12 SMC entry conditions. Returns {condition: (passed, reason)}
    where *reason* is a short human-readable fact explaining the pass/fail.

    Single source of truth — evaluate_conditions() and describe_conditions()
    are thin wrappers over this. Call this directly when you need both the
    bool and the reason and want to avoid evaluating twice.
    """
    cfg = _load_config()
    st  = cfg["strategy"]

    # 1. Weekly macro bias
    weekly_trend = indicators.get("weekly_trend", "ranging")
    weekly_bias = (
        (direction == "call" and weekly_trend == "uptrend") or
        (direction == "put"  and weekly_trend == "downtrend")
    )
    need = "uptrend" if direction == "call" else "downtrend"
    weekly_reason = (f"weekly {weekly_trend} matches {direction}" if weekly_bias
                     else f"weekly {weekly_trend}; {direction} needs {need}")

    # 2. Daily market structure defined (trend or CHOCH)
    trend = indicators.get("market_structure", "ranging")
    choch = bool(indicators.get("choch", False))
    daily_structure = trend != "ranging" or choch
    daily_reason = (f"daily {trend}" + (" + CHOCH" if choch else "")
                    if daily_structure else "daily ranging, no CHOCH")

    # 3. Liquidity sweep completed
    liquidity_sweep = bool(indicators.get("liquidity_swept", False))
    sweep_type = indicators.get("sweep_type")
    sweep_reason = (f"{sweep_type or 'liquidity'} swept" if liquidity_sweep
                    else "no liquidity sweep")

    # 4. Price in Fibonacci 0.618–0.786 zone
    fibonacci_zone = bool(indicators.get("in_fib_zone", False))
    fib_lo = st.get("fib_zone_min", 0.618)
    fib_hi = st.get("fib_zone_max", 0.786)
    fib_reason = (f"in {fib_lo:.3f}-{fib_hi:.3f} zone" if fibonacci_zone
                  else f"outside {fib_lo:.3f}-{fib_hi:.3f} zone")

    # 5. Price at / inside an order block
    ob_quality = indicators.get("order_block_quality", 0.0)
    order_block = ob_quality > 0
    ob_reason = (f"at order block (q={ob_quality:.0f})" if order_block
                 else "not at an order block")

    # 6. Relative volume
    rvol_min = _get_param("rvol_min", st.get("rvol_min", 1.5))
    rvol_val = indicators.get("rvol", 0.0)
    rvol = rvol_val >= rvol_min
    rvol_reason = f"{rvol_val:.2f}x {'>=' if rvol else '<'} {rvol_min:.1f}x"

    # 7. ATR expansion
    atr_min = _get_param("atr_expansion_min", st.get("atr_expansion_min", 1.1))
    atr_val = indicators.get("atr_expansion_ratio", 1.0)
    atr_expansion = atr_val >= atr_min
    atr_reason = f"ratio {atr_val:.2f} {'>=' if atr_expansion else '<'} {atr_min:.2f}"

    # 8. Session timing
    session_min = int(_get_param("session_score_min", st.get("session_score_min", 1)))
    sess_val = indicators.get("session_score", 0)
    session_score = sess_val >= session_min
    sess_reason = f"score {sess_val} {'>=' if session_score else '<'} {session_min}"

    # 9. AI confidence
    conf_min = _get_param("ai_confidence_min", st.get("ai_confidence_min", 0.72))
    ai_confidence = confidence >= conf_min
    conf_reason = f"{confidence*100:.0f}% {'>=' if ai_confidence else '<'} {conf_min*100:.0f}%"

    # 10. Earnings buffer
    buffer = int(_get_param("earnings_buffer_days", st.get("earnings_buffer_days", 5)))
    earnings_clear = not earnings_within_days(ticker, buffer)
    earnings_reason = (f"no earnings within {buffer}d" if earnings_clear
                       else f"earnings within {buffer}d")

    # 11. VIX below max
    vix_max = _get_param("vix_max", st.get("vix_max", 30))
    vix_ok = vix is None or vix < vix_max
    vix_reason = (f"VIX {vix:.1f} {'<' if vix_ok else '>='} {vix_max:.0f}"
                  if vix is not None else "VIX unavailable")

    # 12. Not in last 15 min of trading day
    not_eod = not _is_within_last_15_min()
    eod_reason = "not last 15 min" if not_eod else "within last 15 min"

    return {
        "weekly_bias":     (weekly_bias,     weekly_reason),
        "daily_structure": (daily_structure, daily_reason),
        "liquidity_sweep": (liquidity_sweep, sweep_reason),
        "fibonacci_zone":  (fibonacci_zone,  fib_reason),
        "order_block":     (order_block,     ob_reason),
        "rvol":            (rvol,            rvol_reason),
        "atr_expansion":   (atr_expansion,   atr_reason),
        "session_score":   (session_score,   sess_reason),
        "ai_confidence":   (ai_confidence,   conf_reason),
        "earnings_clear":  (earnings_clear,  earnings_reason),
        "vix_ok":          (vix_ok,          vix_reason),
        "not_eod":         (not_eod,         eod_reason),
    }


def evaluate_conditions(indicators: Dict[str, Any],
                         vix: float,
                         confidence: float,
                         direction: str,
                         ticker: str) -> Dict[str, bool]:
    """
    Evaluate all 12 SMC entry conditions and return {condition: passed}.

    Keys match the signal_candidates table columns (minus the 'cond_' prefix).
    Use this for pass/fail visibility (scanner, near-miss tracking). Call
    all_entry_conditions_met() when you only need the final bool, or
    describe_conditions() when you also want the reason for each.
    """
    detailed = evaluate_conditions_detailed(indicators, vix, confidence,
                                            direction, ticker)
    return {k: passed for k, (passed, _reason) in detailed.items()}


def describe_conditions(indicators: Dict[str, Any],
                        vix: float,
                        confidence: float,
                        direction: str,
                        ticker: str) -> Dict[str, str]:
    """Return {condition: reason} — a short fact explaining each pass/fail."""
    detailed = evaluate_conditions_detailed(indicators, vix, confidence,
                                            direction, ticker)
    return {k: reason for k, (_passed, reason) in detailed.items()}


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
