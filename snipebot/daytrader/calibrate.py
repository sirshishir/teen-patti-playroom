"""calibrate.py — nightly recalibration + triple-barrier labeling.

Runs after close (all of today's data is >15 min old → pure SIP, free):
  1. Measure today's wick overshoots past each reference level  → sweep_samples
  2. Recompute rolling q50/q90 per (ticker, level_type)         → calibration
  3. Label today's pending zone_events via triple-barrier       → zone_events
  4. Recompute respect rates from labeled history               → calibration

The same pure functions are reused by backtest.py in walk-forward mode.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from daytrader import store
from daytrader.data_feed import (get_day_frame_sip, prior_day_hlc,
                                 premarket_slice, rth_slice, session_date_str)
from daytrader.levels_engine import compute_atr, reference_levels, resample_5m
from daytrader.settings import CONFIG

logger = logging.getLogger(__name__)
_C = CONFIG["calibration"]

_SUPPORT = {"PDL", "PML", "OPEN", "RN_BELOW", "VWAP", "LOD"}


# ── pure measurement functions (shared with backtest) ─────────────────────────

def measure_overshoots(df_1m_rth: pd.DataFrame,
                       refs: Dict[str, float]) -> List[Tuple[str, float]]:
    """For each reference level swept-and-reclaimed today, return the max
    wick overshoot fraction of the first sweep episode."""
    out: List[Tuple[str, float]] = []
    if df_1m_rth.empty:
        return out
    lows = df_1m_rth["low"].values
    highs = df_1m_rth["high"].values
    closes = df_1m_rth["close"].values
    n = len(closes)
    reclaim = int(_C["reclaim_bars"])

    for lt, lvl in refs.items():
        if lt in ("HOD", "LOD"):        # defined by today's extremes — skip
            continue
        support = lt in _SUPPORT
        pierce = np.where(lows < lvl)[0] if support else np.where(highs > lvl)[0]
        if len(pierce) == 0:
            continue
        i0 = int(pierce[0])
        win_end = min(n, i0 + reclaim + 1)
        if support:
            depth = (lvl - lows[i0:win_end].min()) / lvl
            reclaimed = (closes[i0:win_end] > lvl).any()
        else:
            depth = (highs[i0:win_end].max() - lvl) / lvl
            reclaimed = (closes[i0:win_end] < lvl).any()
        if reclaimed and depth > 0:
            out.append((lt, round(float(depth), 6)))
    return out


def triple_barrier(df_1m_after: pd.DataFrame, entry: float, upper: float,
                   lower: float, max_minutes: int = None
                   ) -> Tuple[str, float, float, float]:
    """Walk forward bar-by-bar: which barrier is hit first?
    Both-in-one-bar resolves as LOSS (conservative).
    Returns (outcome, minutes, mfe, mae) with mfe/mae in price units."""
    max_minutes = max_minutes or int(_C["time_barrier_minutes"])
    mfe = mae = 0.0
    sub = df_1m_after.iloc[:max_minutes]
    for k, (_, bar) in enumerate(sub.iterrows(), start=1):
        mfe = max(mfe, float(bar["high"]) - entry)
        mae = max(mae, entry - float(bar["low"]))
        hit_up = bar["high"] >= upper
        hit_dn = bar["low"] <= lower
        if hit_dn:                       # conservative: stop first
            return "loss", float(k), mfe, mae
        if hit_up:
            return "win", float(k), mfe, mae
    return "timeout", float(len(sub)), mfe, mae


def rolling_quantiles(samples: List[float]) -> Optional[Tuple[float, float]]:
    if len(samples) < int(_C["min_samples_for_quantiles"]):
        return None
    arr = np.asarray(samples, dtype=float)
    return float(np.quantile(arr, 0.5)), float(np.quantile(arr, 0.9))


# ── nightly job ───────────────────────────────────────────────────────────────

def run_nightly(session_date: Optional[str] = None) -> Dict[str, int]:
    session_date = session_date or session_date_str()
    tickers = CONFIG["tickers"]
    stats = {"samples": 0, "labeled": 0}

    for ticker in tickers:
        df = get_day_frame_sip(ticker, session_date)
        if df is None or df.empty:
            logger.warning("nightly: no SIP data for %s %s", ticker, session_date)
            continue
        rth = rth_slice(df)
        if rth.empty:
            continue
        pm = premarket_slice(df)
        price_close = float(rth["close"].iloc[-1])
        refs = reference_levels(ticker, price_close, rth, pm,
                                prior_day_hlc(ticker, session_date))

        # 1. overshoot samples
        rows = [{"ticker": ticker, "session_date": session_date,
                 "level_type": lt, "overshoot": ov}
                for lt, ov in measure_overshoots(rth, refs)]
        if rows:
            store.insert_sweep_samples(rows)
            stats["samples"] += len(rows)

        # 3. label pending events with today's true 1-min path
        for ev in [e for e in store.pending_events(session_date)
                   if e["ticker"] == ticker]:
            touch = pd.Timestamp(ev["touch_time"])
            if touch.tzinfo is None:
                touch = touch.tz_localize("UTC")
            after = rth[rth.index > touch.tz_convert(rth.index.tz)]
            if after.empty:
                continue
            entry = float(ev["touch_price"])
            if ev["direction"] == "long":
                up, dn = float(ev["target1"]), float(ev["stop"])
            else:
                up, dn = float(ev["stop"]), float(ev["target1"])
                # short: 'win' means lower barrier — swap semantics below
            outcome, mins, mfe, mae = triple_barrier(after, entry, up, dn)
            if ev["direction"] == "short" and outcome in ("win", "loss"):
                outcome = "win" if outcome == "loss" else "loss"
            store.label_event(ev["id"], outcome, mins, mfe, mae)
            stats["labeled"] += 1

        # 2 + 4. quantiles + respect rates
        _refresh_calibration(ticker)

    logger.info("nightly calibration %s: %s", session_date, stats)
    return stats


def _refresh_calibration(ticker: str) -> None:
    window = int(_C["window_sessions"])
    labeled = [e for e in store.labeled_events() if e["ticker"] == ticker]
    by_type_lab: Dict[str, List[str]] = {}
    for e in labeled:
        by_type_lab.setdefault(e["level_type"], []).append(e["outcome"])

    level_types = set(list(by_type_lab) + ["PDL", "PML", "OPEN", "RN_BELOW",
                                           "VWAP", "PDH", "PMH", "RN_ABOVE"])
    now = datetime.now(timezone.utc).isoformat()
    for lt in level_types:
        samples = store.sweep_samples(ticker, lt, window)
        qq = rolling_quantiles(samples)
        q50, q90 = qq if qq else (float(_C["default_q50"]), float(_C["default_q90"]))
        outs = by_type_lab.get(lt, [])
        wins = outs.count("win")
        losses = outs.count("loss")
        respect = wins / (wins + losses) if (wins + losses) >= 5 else None
        store.upsert_calibration(ticker, lt, round(q50, 6), round(q90, 6),
                                 respect if respect is not None else -1.0,
                                 len(samples), wins + losses, now)


def load_calibration(ticker: str) -> Dict[str, Dict]:
    calib = store.get_calibration(ticker)
    for row in calib.values():                      # -1 sentinel → None
        if row.get("respect_rate", -1.0) is not None and row["respect_rate"] < 0:
            row["respect_rate"] = None
    return calib
