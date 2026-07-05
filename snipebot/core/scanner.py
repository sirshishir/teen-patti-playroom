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

import pandas as pd
import pytz
import yaml

from core.indicators import compute_all_indicators
from core.risk_manager import evaluate_and_queue, daily_loss_limit_hit
from core.strategy import (
    all_entry_conditions_met, evaluate_conditions, describe_conditions,
    evaluate_conditions_detailed, detect_direction, build_signal,
    signal_to_trade_record, halt_file_exists,
)
from data import database as db
from data.market_data import (
    fetch_ohlcv, get_cached_analysis, build_ticker_analysis, fetch_vix,
    fetch_options_chain, select_option_contract,
)
from ml.confidence_model import get_confidence_score
from notifications import discord_bot
from core.order_executor import place_option_order

logger = logging.getLogger(__name__)

_ET        = pytz.timezone("US/Eastern")
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

    # FIX-4: VIX gate must fail CLOSED. A data outage must never *enable*
    # trading, so a missing VIX halts the whole cycle rather than defaulting to
    # a passing value.
    vix = fetch_vix()
    if vix is None:
        logger.error("VIX unavailable — halting scan cycle (fail-closed)")
        discord_bot.send_system_alert("data_error", "VIX", {})
        return

    cfg = _load_config()

    for ticker in db.get_watchlist():
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

        # ── FIX-3: evaluate on COMPLETED bars only ──────────────────────────
        # The bar forming at :00/:30 is partial — RVOL is understated ~2x and a
        # "sweep + close back inside" can repaint when the bar completes. Drop
        # the in-progress bar for analysis, but keep its close as the live price.
        current_price = float(df["close"].iloc[-1])
        bar_span = pd.Timedelta(hours=1)
        if pd.Timestamp.now(tz="UTC") < df.index[-1] + bar_span:
            df_eval = df.iloc[:-1]
        else:
            df_eval = df

        # ── Compute all SMC indicators ──────────────────────────────────────
        indicators = compute_all_indicators(df_eval, cached)
        indicators["current_price"] = current_price   # freshest price wins

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

        # ── Near-miss Discord alert (per-ticker threshold, DB-overridable) ──
        default_threshold = cfg["strategy"].get("near_miss_discord_threshold", 9)
        near_miss_threshold = db.get_near_miss_threshold(ticker, default_threshold)
        if near_miss_threshold <= conditions_met < 12:
            cond_reasons = describe_conditions(indicators, vix, confidence,
                                               direction, ticker)
            discord_bot.send_near_miss_signal(
                ticker, direction, conditions_met, cond_results,
                indicators, confidence, vix, cond_reasons,
            )

        # ── FIX-10: seed the learner with virtual near-miss paper trades ────
        # Paper-mode only. Records a virtual (is_seed=1) position — monitored by
        # the position monitor like a paper trade but NEVER sent to the broker —
        # so the RF model has enough samples to leave cold start.
        seed_mode = cfg.get("ml", {}).get("seed_mode", False)
        seed_min  = cfg.get("ml", {}).get("seed_min_conditions", 10)
        paper     = os.getenv("TRADING_MODE", "paper").lower() == "paper"
        if (seed_mode and paper and seed_min <= conditions_met < 12
                and not db.seeded_ticker_today(ticker)):
            _record_seed_trade(ticker, indicators, confidence, vix, direction, cfg)

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


# ── On-demand analysis (read-only, no orders) ───────────────────────────────

def analyze_ticker(ticker: str, vix: float, fresh: bool = True,
                   vix_assumed: bool = False) -> Dict:
    """
    Read-only SMC analysis for a single ticker. Places no orders and writes
    nothing to the DB.

    fresh=True  → recompute the full multi-timeframe analysis live (used by
                  /analysis so the numbers are current, not from the 9 AM cache).
    fresh=False → use the cached daily analysis (cheaper).
    vix_assumed → True if *vix* is a fallback value (real VIX was unavailable);
                  the vix_ok reason is annotated accordingly (FIX-4).
    """
    ticker = ticker.strip().upper()
    try:
        df = fetch_ohlcv(ticker, interval="1Hour", period_days=20)
        if fresh:
            analysis = build_ticker_analysis(ticker)
        else:
            analysis = get_cached_analysis(ticker)
        if df is None or df.empty or not analysis:
            return {"ticker": ticker, "available": False}

        indicators = compute_all_indicators(df, analysis)
        direction  = detect_direction(indicators)
        # Fall back to the structure-implied side so we can still show a full
        # breakdown even when there's no clean directional setup.
        eval_dir = direction or (
            "call" if indicators.get("market_structure") == "uptrend" else "put"
        )
        confidence = get_confidence_score(
            indicators, vix, eval_dir, datetime.now(timezone.utc))
        detailed = evaluate_conditions_detailed(
            indicators, vix, confidence, eval_dir, ticker)
        conds   = {k: passed for k, (passed, _r) in detailed.items()}
        reasons = {k: reason for k, (_p, reason) in detailed.items()}
        if vix_assumed:
            reasons["vix_ok"] = "VIX unavailable (assumed)"

        return {
            "ticker":         ticker,
            "available":      True,
            "direction":      direction,           # None if no clean setup
            "price":          indicators.get("current_price"),
            "weekly_trend":   indicators.get("weekly_trend"),
            "structure":      indicators.get("market_structure"),
            "rvol":           indicators.get("rvol"),
            "confidence":     confidence,
            "conditions":     conds,
            "reasons":        reasons,
            "conditions_met": sum(1 for v in conds.values() if v),
        }
    except Exception as exc:
        logger.error("analyze_ticker error for %s: %s", ticker, exc)
        return {"ticker": ticker, "available": False}


def analyze_watchlist(tickers: List[str] = None, fresh: bool = True) -> List[Dict]:
    """
    Read-only SMC analysis for a list of tickers (defaults to the dynamic
    watchlist). Used by the Discord /analysis command.
    """
    # Read-only path: unlike run_scan (which fails closed), keep a 15.0 fallback
    # so /analysis still renders — but flag it so the vix_ok reason says so.
    vix = fetch_vix()
    vix_assumed = vix is None
    if vix_assumed:
        vix = 15.0
    if tickers is None:
        tickers = db.get_watchlist()

    results: List[Dict] = []
    for ticker in tickers:
        time.sleep(0.2)  # rate-limit
        results.append(analyze_ticker(ticker, vix, fresh=fresh,
                                      vix_assumed=vix_assumed))
    return results


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
        max_spread = cfg["strategy"].get("max_spread_pct", 0.08)
        chain   = fetch_options_chain(ticker, min_dte=min_dte, max_dte=max_dte)
        if chain is None or chain.empty:
            logger.warning("No options chain for %s", ticker)
            return None
        contract = select_option_contract(chain, direction, current_price,
                                          max_spread_pct=max_spread)
        if contract is None:
            logger.warning("No suitable contract for %s %s", ticker, direction)
        return contract
    except Exception as exc:
        logger.error("Options chain error for %s: %s", ticker, exc)
        return None


def _notify_entry(signal: Dict, indicators: Dict, is_seed: bool = False) -> None:
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
        is_seed     = is_seed,
    )


def _record_seed_trade(ticker: str, indicators: Dict, confidence: float,
                       vix: float, direction: str, cfg: Dict) -> None:
    """
    Record a virtual (is_seed=1) paper trade for a near-miss setup. Builds the
    same signal payload and picks a real contract so the position monitor can
    track it, but never places a broker order (FIX-10).
    """
    try:
        signal = build_signal(ticker, indicators, confidence, vix, direction)
        contract = _pick_contract(ticker, direction,
                                  indicators["current_price"], cfg)
        if contract is None:
            return
        signal["option_symbol"] = contract["symbol"]
        signal["strike"]        = contract["strike"]
        signal["expiry"]        = contract["expiry"]
        signal["dte"]           = contract["dte"]
        signal["premium"]       = contract["premium"]
        signal["qty"]           = 1
        record   = signal_to_trade_record(signal, is_seed=True)
        trade_id = db.insert_trade(record)
        logger.info("🧪 SEED trade recorded: id=%d %s %s", trade_id, ticker, direction)
        _notify_entry(signal, indicators, is_seed=True)
    except Exception as exc:
        logger.error("Seed trade recording failed for %s: %s", ticker, exc)


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
