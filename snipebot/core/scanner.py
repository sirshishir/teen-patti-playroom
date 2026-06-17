"""
scanner.py — 30-minute SMC market scanner (1-hour bar entry trigger).

Appropriate for 14–30 DTE options: uses 1-hour bars for entry timing,
daily bars for structure/OBs/Fib (pre-cached at 9 AM), weekly bars for bias.

Runs every 30 minutes during market hours (9:30–3:30 ET, Mon–Fri).
Data-fetch failure tracking: 3 consecutive failures → Discord alert + 15-min pause.
"""

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

import pytz
import yaml

from core.indicators import compute_all_indicators
from core.risk_manager import evaluate_and_queue, daily_loss_limit_hit
from core.strategy import (
    all_entry_conditions_met, evaluate_conditions, detect_direction,
    build_signal, signal_to_trade_record, halt_file_exists,
)
from data import database as db
from data.market_data import (
    fetch_ohlcv, get_cached_analysis, fetch_vix,
    fetch_options_chain, select_option_contract,
)
from ml.confidence_model import get_confidence_score
from notifications import discord_bot
from core.order_executor import place_option_order

logger = logging.getLogger(__name__)

_ET        = pytz.timezone("US/Eastern")
_WATCHLIST = ["GOOGL", "MSFT", "TSLA", "AAPL", "SPY"]
_BASE_DIR  = os.path.dirname(os.path.dirname(__file__))

# Per-ticker failure / pause state
_fetch_failure_count: Dict[str, int]   = defaultdict(int)
_pause_until:         Dict[str, float] = {}

# Session counters (reset by daily_report)
_scan_signals_count = 0
_scan_fired_count   = 0
_scan_avg_confidence: List[float] = []


def get_session_stats() -> Dict:
    avg_conf = (
        round(sum(_scan_avg_confidence) / len(_scan_avg_confidence) * 100, 1)
        if _scan_avg_confidence else 0.0
    )
    return {
        "signals_scanned": _scan_signals_count,
        "fired":           _scan_fired_count,
        "avg_confidence":  avg_conf,
    }


def reset_session_stats() -> None:
    global _scan_signals_count, _scan_fired_count, _scan_avg_confidence
    _scan_signals_count = 0
    _scan_fired_count   = 0
    _scan_avg_confidence = []


# ── Main scan loop ────────────────────────────────────────────────────────────

def run_scan() -> None:
    global _scan_signals_count, _scan_fired_count

    if halt_file_exists():
        logger.info("HALT file present — skipping scan")
        return
    if daily_loss_limit_hit():
        logger.warning("Daily loss limit hit — skipping scan")
        return

    now_et = datetime.now(_ET)
    logger.info("SMC scan started at %s ET", now_et.strftime("%H:%M:%S"))

    vix = fetch_vix()
    if vix is None:
        logger.warning("VIX unavailable — using 15.0")
        vix = 15.0

    cfg = _load_config()

    for ticker in _WATCHLIST:
        time.sleep(0.2)  # Alpaca rate-limit

        if _is_paused(ticker):
            logger.info("%s paused (data errors) — skipping", ticker)
            continue

        # ── Fetch 1-hour bars (entry trigger timeframe) ─────────────────────
        df = _safe_fetch_ohlcv(ticker)
        if df is None:
            continue
        _fetch_failure_count[ticker] = 0

        # ── Get daily analysis cache ────────────────────────────────────────
        cached = get_cached_analysis(ticker)
        if not cached:
            logger.debug("No daily cache for %s — skipping until 9 AM cache runs", ticker)
            continue

        # ── Compute all SMC indicators ──────────────────────────────────────
        indicators = compute_all_indicators(df, cached)

        # ── Determine direction ─────────────────────────────────────────────
        direction = detect_direction(indicators)
        if direction is None:
            continue

        # ── Confidence score ────────────────────────────────────────────────
        signal_time = datetime.now(timezone.utc)
        confidence  = get_confidence_score(indicators, vix, direction, signal_time)
        _scan_avg_confidence.append(confidence)
        _scan_signals_count += 1

        # ── Evaluate all 12 conditions individually ─────────────────────────
        cond_results   = evaluate_conditions(indicators, vix, confidence, direction, ticker)
        conditions_met = sum(1 for v in cond_results.values() if v)

        logger.info(
            "Signal candidate: %s %s | %d/12 conditions | struct=%s sweep=%s "
            "fib=%s OB_q=%.2f RVOL=%.2f ATR_exp=%s sess=%d conf=%.2f",
            ticker, direction, conditions_met,
            indicators.get("market_structure"),
            indicators.get("sweep_type"),
            indicators.get("in_fib_zone"),
            indicators.get("order_block_quality", 0),
            indicators.get("rvol", 0),
            indicators.get("atr_expanding"),
            indicators.get("session_score", 0),
            confidence,
        )

        # ── Record candidate to DB (every scan, regardless of outcome) ─────
        candidate_id = db.insert_signal_candidate({
            "ticker":               ticker,
            "direction":            direction,
            "scan_time":            signal_time.isoformat(),
            "entry_price":          indicators.get("current_price"),
            "conditions_met":       conditions_met,
            "cond_weekly_bias":     int(cond_results["weekly_bias"]),
            "cond_daily_structure": int(cond_results["daily_structure"]),
            "cond_liquidity_sweep": int(cond_results["liquidity_sweep"]),
            "cond_fibonacci_zone":  int(cond_results["fibonacci_zone"]),
            "cond_order_block":     int(cond_results["order_block"]),
            "cond_rvol":            int(cond_results["rvol"]),
            "cond_atr_expansion":   int(cond_results["atr_expansion"]),
            "cond_session_score":   int(cond_results["session_score"]),
            "cond_ai_confidence":   int(cond_results["ai_confidence"]),
            "cond_earnings_clear":  int(cond_results["earnings_clear"]),
            "cond_vix_ok":          int(cond_results["vix_ok"]),
            "cond_not_eod":         int(cond_results["not_eod"]),
            "ai_confidence_score":  confidence,
            "fired":                0,
        })

        # ── Near-miss Discord alert ─────────────────────────────────────────
        near_miss_threshold = cfg["strategy"].get("near_miss_discord_threshold", 9)
        if near_miss_threshold <= conditions_met < 12:
            discord_bot.send_near_miss_signal(
                ticker, direction, conditions_met, cond_results,
                indicators, confidence, vix,
            )

        # ── Full entry gate ─────────────────────────────────────────────────
        if halt_file_exists() or conditions_met < 12:
            continue

        if db.traded_ticker_today(ticker):
            logger.info("%s already traded today — skip", ticker)
            continue

        # ── Build signal ────────────────────────────────────────────────────
        signal = build_signal(ticker, indicators, confidence, vix, direction)

        # ── Options chain lookup ────────────────────────────────────────────
        contract = _pick_contract(ticker, direction, indicators["current_price"],
                                   cfg)
        if contract is None:
            continue

        signal["option_symbol"] = contract["symbol"]
        signal["strike"]        = contract["strike"]
        signal["expiry"]        = contract["expiry"]
        signal["dte"]           = contract["dte"]
        signal["premium"]       = contract["premium"]

        # ── Risk gate ───────────────────────────────────────────────────────
        if not evaluate_and_queue(signal):
            continue

        # ── Place order ─────────────────────────────────────────────────────
        order_id = place_option_order(signal)
        if order_id is None:
            logger.error("Order placement failed for %s %s", ticker, direction)
            continue

        # ── Record in DB ────────────────────────────────────────────────────
        record   = signal_to_trade_record(signal)
        trade_id = db.insert_trade(record)
        db.update_candidate_fired(candidate_id)
        logger.info("Trade recorded: id=%d %s %s conf=%.2f",
                    trade_id, ticker, direction, confidence)
        _scan_fired_count += 1

        # ── Discord entry notification ──────────────────────────────────────
        _notify_entry(signal, indicators)

    logger.info("Scan complete. Fired %d/%d signals this cycle.",
                _scan_fired_count, _scan_signals_count)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_config() -> Dict:
    with open(os.path.join(_BASE_DIR, "config.yaml")) as f:
        return yaml.safe_load(f)


def _pick_contract(ticker: str, direction: str,
                   current_price: float, cfg: Dict):
    """Fetch options chain and select the best ATM/OTM contract."""
    try:
        min_dte = cfg["strategy"]["min_dte"]
        max_dte = cfg["strategy"]["max_dte"]
        chain   = fetch_options_chain(ticker, min_dte=min_dte, max_dte=max_dte)
        if chain is None or chain.empty:
            logger.warning("No options chain for %s", ticker)
            return None
        contract = select_option_contract(chain, direction, current_price)
        if contract is None:
            logger.warning("No suitable contract for %s %s", ticker, direction)
        return contract
    except Exception as exc:
        logger.error("Options chain error for %s: %s", ticker, exc)
        return None


def _notify_entry(signal: Dict, indicators: Dict) -> None:
    fib   = indicators.get("fib") or {}
    ob    = indicators.get("nearest_ob") or {}
    discord_bot.send_trade_entry(
        ticker      = signal["ticker"],
        direction   = signal["direction"],
        strike      = signal.get("strike", 0),
        expiry      = signal.get("expiry", ""),
        dte         = signal.get("dte", 0),
        premium     = signal.get("premium", 0),
        qty         = signal.get("qty", 1),
        total_cost  = signal.get("total_cost", 0),
        rsi         = 0.0,                              # not used in SMC
        macd_signal = indicators.get("sweep_type", ""),
        vol_ratio   = indicators.get("rvol", 0),
        confidence  = signal.get("ai_confidence", 0) * 100,
        zone_low    = ob.get("low", 0),
        zone_high   = ob.get("high", 0),
        zone_touches = int(indicators.get("order_block_quality", 0)),
    )


def _safe_fetch_ohlcv(ticker: str):
    df = fetch_ohlcv(ticker, interval="1Hour", period_days=20)
    if df is None or df.empty:
        _fetch_failure_count[ticker] += 1
        logger.warning("%s fetch failed (count=%d)", ticker,
                       _fetch_failure_count[ticker])
        if _fetch_failure_count[ticker] >= 3:
            _pause_until[ticker]        = time.time() + 15 * 60
            _fetch_failure_count[ticker] = 0
            discord_bot.send_system_alert("data_error", ticker, {})
        return None
    return df


def _is_paused(ticker: str) -> bool:
    resume_at = _pause_until.get(ticker, 0)
    if time.time() < resume_at:
        return True
    _pause_until.pop(ticker, None)
    return False
