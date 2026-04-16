"""
scanner.py — 5-minute market scanner.

Runs every 5 minutes during market hours (9:35–3:45 ET, Mon–Fri).
Scans each watchlist ticker against all entry conditions and fires orders
when every condition is satisfied.

Failure tracking: if any ticker fails data-fetch 3× in a row, send Discord
alert and pause scanning for 15 minutes.
"""

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

import pytz

from core.indicators import compute_all_indicators, price_in_zone
from core.risk_manager import evaluate_and_queue, daily_loss_limit_hit
from core.strategy import (
    all_entry_conditions_met, detect_direction,
    build_signal, signal_to_trade_record, halt_file_exists,
)
from data import database as db
from data.market_data import (
    fetch_ohlcv, get_cached_sr_zones, fetch_vix,
    fetch_options_chain, select_option_contract,
)
from ml.confidence_model import get_confidence_score
from ml.feature_engineer import build_feature_vector
from notifications import discord_bot
from core.order_executor import place_option_order

logger = logging.getLogger(__name__)

_ET = pytz.timezone("US/Eastern")
_WATCHLIST = ["GOOGL", "MSFT", "TSLA", "AAPL", "SPY"]

# State tracking
_fetch_failure_count: Dict[str, int] = defaultdict(int)
_pause_until: Dict[str, float] = {}  # ticker → Unix timestamp when pause ends

# Session counters (reset on daily_report)
_scan_signals_count = 0
_scan_fired_count = 0
_scan_avg_confidence: List[float] = []


def get_session_stats() -> Dict:
    avg_conf = (
        round(sum(_scan_avg_confidence) / len(_scan_avg_confidence) * 100, 1)
        if _scan_avg_confidence else 0.0
    )
    return {
        "signals_scanned": _scan_signals_count,
        "fired": _scan_fired_count,
        "avg_confidence": avg_conf,
    }


def reset_session_stats() -> None:
    global _scan_signals_count, _scan_fired_count, _scan_avg_confidence
    _scan_signals_count = 0
    _scan_fired_count = 0
    _scan_avg_confidence = []


def run_scan() -> None:
    """Entry point called by APScheduler every 5 minutes."""
    global _scan_signals_count, _scan_fired_count

    if halt_file_exists():
        logger.info("HALT file present — skipping scan")
        return

    if daily_loss_limit_hit():
        logger.warning("Daily loss limit hit — skipping scan")
        return

    now_et = datetime.now(_ET)
    logger.info("Scan started at %s ET", now_et.strftime("%H:%M:%S"))

    # Fetch VIX once per scan cycle
    vix = fetch_vix()
    if vix is None:
        logger.warning("VIX unavailable — using 15.0 as fallback")
        vix = 15.0

    for ticker in _WATCHLIST:
        time.sleep(0.2)  # rate-limit Alpaca calls

        # Check pause
        if _is_paused(ticker):
            logger.info("%s is paused (data errors) — skipping", ticker)
            continue

        # Fetch OHLCV
        df = _safe_fetch_ohlcv(ticker)
        if df is None:
            continue

        _fetch_failure_count[ticker] = 0  # reset on success

        # Get cached S/R zones
        sr_zones = get_cached_sr_zones(ticker)
        if not sr_zones:
            logger.debug("No S/R zones cached for %s", ticker)
            continue

        # Compute all indicators
        indicators = compute_all_indicators(df, sr_zones)
        if not indicators["in_sr_zone"]:
            continue  # price not near any zone — skip

        # Determine trade direction
        direction = detect_direction(indicators)
        if direction is None:
            continue  # ambiguous — no trade

        # Compute confidence
        signal_time = datetime.now(timezone.utc)
        confidence = get_confidence_score(indicators, vix, direction, signal_time)
        _scan_avg_confidence.append(confidence)
        _scan_signals_count += 1

        logger.info("Signal candidate: %s %s RSI=%.1f conf=%.2f vol=%.2fx",
                    ticker, direction, indicators["rsi"], confidence,
                    indicators["volume_ratio"])

        # All entry conditions gate
        if not all_entry_conditions_met(indicators, vix, confidence, direction, ticker):
            continue

        # Already traded this ticker today?
        if db.traded_ticker_today(ticker):
            logger.info("%s already traded today — skip", ticker)
            continue

        # Build signal
        nearest_zone = indicators.get("nearest_zone") or {}
        signal = build_signal(ticker, nearest_zone, indicators, confidence, vix, direction)

        # Options chain lookup
        try:
            import yaml
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")) as f:
                cfg = yaml.safe_load(f)
            min_dte = cfg["strategy"]["min_dte"]
            max_dte = cfg["strategy"]["max_dte"]

            chain = fetch_options_chain(ticker, min_dte=min_dte, max_dte=max_dte)
            if chain is None or chain.empty:
                logger.warning("No options chain for %s — skipping", ticker)
                continue

            current_price = indicators["current_price"]
            contract = select_option_contract(chain, direction, current_price)
            if contract is None:
                logger.warning("No suitable contract found for %s %s", ticker, direction)
                continue

            signal["option_symbol"] = contract["symbol"]
            signal["strike"] = contract["strike"]
            signal["expiry"] = contract["expiry"]
            signal["dte"] = contract["dte"]
            signal["premium"] = contract["premium"]
        except Exception as exc:
            logger.error("Options chain error for %s: %s", ticker, exc)
            continue

        # Risk gate (position sizing, daily loss, max positions)
        if not evaluate_and_queue(signal):
            continue

        # Place order
        order_id = place_option_order(signal)
        if order_id is None:
            logger.error("Order placement failed for %s %s", ticker, direction)
            continue

        # Record in DB
        record = signal_to_trade_record(signal)
        # Store extra fields needed by risk_manager
        trade_id = db.insert_trade(record)
        logger.info("Trade recorded: id=%d %s %s conf=%.2f",
                    trade_id, ticker, direction, confidence)

        _scan_fired_count += 1

        # Discord entry notification
        discord_bot.send_trade_entry(
            ticker=ticker,
            direction=direction,
            strike=signal["strike"],
            expiry=signal["expiry"],
            dte=signal["dte"],
            premium=signal["premium"],
            qty=signal["qty"],
            total_cost=signal["total_cost"],
            rsi=indicators["rsi"],
            macd_signal=indicators.get("macd_crossover", "neutral"),
            vol_ratio=indicators["volume_ratio"],
            confidence=confidence * 100,
            zone_low=nearest_zone.get("low", 0.0),
            zone_high=nearest_zone.get("high", 0.0),
            zone_touches=nearest_zone.get("touches", 0),
        )

    logger.info("Scan complete. Fired %d signal(s) this scan.", _scan_fired_count)


# ── Data fetch with failure tracking ─────────────────────────────────────────

def _safe_fetch_ohlcv(ticker: str):
    df = fetch_ohlcv(ticker, interval="5Min", period_days=5)
    if df is None or df.empty:
        _fetch_failure_count[ticker] += 1
        logger.warning("%s fetch failed (count=%d)", ticker, _fetch_failure_count[ticker])
        if _fetch_failure_count[ticker] >= 3:
            _pause_until[ticker] = time.time() + 15 * 60  # 15 minutes
            _fetch_failure_count[ticker] = 0
            discord_bot.send_system_alert(
                alert_type="data_error",
                ticker=ticker,
                extra={},
            )
        return None
    return df


def _is_paused(ticker: str) -> bool:
    resume_at = _pause_until.get(ticker, 0)
    if time.time() < resume_at:
        return True
    if ticker in _pause_until:
        del _pause_until[ticker]
    return False
