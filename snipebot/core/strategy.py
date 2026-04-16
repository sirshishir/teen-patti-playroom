"""
strategy.py — Entry and exit decision logic for SnipeBot.

all_entry_conditions_met() is the main gate.
build_signal() assembles the trade signal dict passed to order_executor.
"""

import logging
import os
from datetime import datetime, time as dt_time, timezone
from typing import Dict, Any, List, Optional

import pytz
import yaml

from core.indicators import compute_all_indicators
from data import database as db
from data.market_data import fetch_vix, earnings_within_days

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_ET = pytz.timezone("US/Eastern")
_HALT_FILE = os.path.join(_BASE_DIR, "HALT.txt")


def _load_config() -> Dict:
    with open(os.path.join(_BASE_DIR, "config.yaml")) as f:
        return yaml.safe_load(f)


def _get_param(name: str, config_value: float) -> float:
    val = db.get_strategy_param(name)
    return val if val is not None else config_value


def halt_file_exists() -> bool:
    return os.path.exists(_HALT_FILE)


def _is_within_last_15_min() -> bool:
    """Return True if current ET time is after 3:45 PM (no new orders)."""
    now_et = datetime.now(_ET).time()
    cutoff = dt_time(15, 45)
    return now_et >= cutoff


# ── Entry Conditions ──────────────────────────────────────────────────────────

def all_entry_conditions_met(indicators: Dict[str, Any],
                               vix: float,
                               confidence: float,
                               direction: str,
                               ticker: str) -> bool:
    """
    Check ALL 8 entry conditions simultaneously.
    Returns True only if every condition passes.
    """
    cfg = _load_config()

    # 0. HALT file check
    if halt_file_exists():
        logger.info("HALT file detected — skipping all signals")
        return False

    # 1. Price in S/R zone
    if not indicators.get("in_sr_zone", False):
        return False

    # 2. RSI threshold
    rsi = indicators["rsi"]
    rsi_oversold = _get_param("rsi_oversold", cfg["strategy"]["rsi_oversold"])
    rsi_overbought = _get_param("rsi_overbought", cfg["strategy"]["rsi_overbought"])
    if direction == "call" and rsi >= rsi_oversold:
        return False
    if direction == "put" and rsi <= rsi_overbought:
        return False

    # 3. MACD crossover in trade direction
    crossover = indicators.get("macd_crossover", "neutral")
    if direction == "call" and crossover != "bullish":
        return False
    if direction == "put" and crossover != "bearish":
        return False

    # 4. Volume spike
    vol_min = _get_param("volume_ratio_min", cfg["strategy"]["volume_ratio_min"])
    if indicators["volume_ratio"] < vol_min:
        return False

    # 5. AI confidence threshold
    conf_min = _get_param("ai_confidence_min", cfg["strategy"]["ai_confidence_min"])
    if confidence < conf_min:
        return False

    # 6. No earnings within buffer days
    buffer = int(_get_param("earnings_buffer_days", cfg["strategy"]["earnings_buffer_days"]))
    if earnings_within_days(ticker, buffer):
        logger.info("Earnings within %d days for %s — skip", buffer, ticker)
        return False

    # 7. VIX below max
    vix_max = _get_param("vix_max", cfg["strategy"]["vix_max"])
    if vix is not None and vix >= vix_max:
        return False

    # 8. Not within last 15 min of trading day
    if _is_within_last_15_min():
        return False

    return True


# ── Direction Detection ───────────────────────────────────────────────────────

def detect_direction(indicators: Dict[str, Any]) -> Optional[str]:
    """
    Determine trade direction ('call' or 'put') from indicator alignment.
    Returns None if direction is ambiguous.
    """
    rsi = indicators["rsi"]
    crossover = indicators.get("macd_crossover", "neutral")

    bullish_rsi = rsi < 40
    bearish_rsi = rsi > 60
    bullish_macd = crossover == "bullish"
    bearish_macd = crossover == "bearish"

    if bullish_rsi and bullish_macd:
        return "call"
    if bearish_rsi and bearish_macd:
        return "put"
    return None


# ── Signal Builder ────────────────────────────────────────────────────────────

def build_signal(ticker: str,
                 zone: Dict,
                 indicators: Dict[str, Any],
                 confidence: float,
                 vix: float,
                 direction: str) -> Dict[str, Any]:
    """
    Assemble the trade signal dict. Does NOT include option contract details —
    those are added by scanner.py after options chain lookup.
    """
    cfg = _load_config()
    now_utc = datetime.now(timezone.utc)
    regime = indicators.get("market_regime", "ranging")

    return {
        "ticker": ticker,
        "direction": direction,
        "signal_time": now_utc.isoformat(),
        "current_price": indicators["current_price"],
        "rsi": indicators["rsi"],
        "macd_crossover": indicators.get("macd_crossover", "neutral"),
        "macd_histogram": indicators.get("macd_histogram", 0.0),
        "volume_ratio": indicators["volume_ratio"],
        "sr_zone": zone,
        "sr_zone_quality": zone.get("quality", 0.0),
        "vix": vix,
        "ai_confidence": confidence,
        "market_regime": regime,
        # Filled by scanner after options chain lookup:
        "option_symbol": None,
        "strike": None,
        "expiry": None,
        "dte": None,
        "premium": None,
        "qty": None,
        "total_cost": None,
    }


# ── Trade Record Builder ──────────────────────────────────────────────────────

def signal_to_trade_record(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an approved signal into a DB trade insert record."""
    from datetime import date
    return {
        "ticker": signal["ticker"],
        "direction": signal["direction"],
        "entry_price": signal.get("premium"),
        "exit_price": None,
        "entry_date": date.today().isoformat(),
        "exit_date": None,
        "pnl": None,
        "pnl_pct": None,
        "exit_reason": None,
        "rsi_at_entry": signal.get("rsi"),
        "macd_signal": signal.get("macd_crossover"),
        "volume_ratio": signal.get("volume_ratio"),
        "sr_zone_quality": signal.get("sr_zone_quality"),
        "vix_at_entry": signal.get("vix"),
        "ai_confidence": signal.get("ai_confidence"),
        "market_regime": signal.get("market_regime"),
        "outcome": None,
    }
