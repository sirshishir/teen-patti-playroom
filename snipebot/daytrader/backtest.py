"""backtest.py — one-time walk-forward validation of the levels strategy.

Replays 1-min SIP history session by session with strict point-in-time
discipline: zones for day D are built from calibration learned on days < D
(seeded with config defaults), then day D's touches are triple-barrier
labeled and only afterwards folded into the rolling quantiles.

Usage (from the snipebot directory):
    python -m daytrader.backtest --start 2025-01-02 --end 2025-06-30
    python -m daytrader.backtest --start 2025-01-02 --end 2025-06-30 --commit

--commit writes the final sweep samples + calibration into daytrader.db so
the live bot starts with seeded quantiles instead of config defaults.
"""

import argparse
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from daytrader import store
from daytrader.calibrate import (measure_overshoots, rolling_quantiles,
                                 triple_barrier)
from daytrader.data_feed import (get_day_frame_sip, premarket_slice,
                                 prior_day_hlc, rth_slice)
from daytrader.levels_engine import (build_zones, compute_atr, compute_rvol,
                                     reference_levels, resample_5m)
from daytrader.scorer import heuristic_score
from daytrader.settings import CONFIG, ET

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backtest")

_C = CONFIG["calibration"]


def trading_sessions(start: str, end: str) -> List[str]:
    """Approximate NYSE sessions via SPY daily SIP bars."""
    from daytrader.data_feed import _fetch
    from alpaca.data.timeframe import TimeFrame
    s = ET.localize(datetime.strptime(start, "%Y-%m-%d")).astimezone(timezone.utc)
    e = ET.localize(datetime.strptime(end, "%Y-%m-%d")).astimezone(timezone.utc)
    got = _fetch(["SPY"], s, e, "sip", timeframe=TimeFrame.Day)
    df = got.get("SPY")
    if df is None or df.empty:
        return []
    return sorted(df.index.tz_convert(ET).strftime("%Y-%m-%d").unique())


def run(start: str, end: str, tickers: List[str], commit: bool,
        min_conf: Optional[float] = None, equity_start: float = 1000.0,
        risk_frac: float = 0.01, cost_r: float = 0.05) -> str:
    if min_conf is None:
        min_conf = float(CONFIG["scorer"]["min_confidence_alert"])
    sessions = trading_sessions(start, end)
    print(f"Backtesting {len(sessions)} sessions × {tickers}")

    # rolling walk-forward calibration state
    window = int(_C["window_sessions"])
    samples: Dict[tuple, deque] = defaultdict(lambda: deque(maxlen=window * 3))
    outcomes: Dict[tuple, deque] = defaultdict(lambda: deque(maxlen=200))
    results: List[Dict] = []

    for si, sd in enumerate(sessions):
        for ticker in tickers:
            df = get_day_frame_sip(ticker, sd)
            if df is None or df.empty:
                continue
            rth = rth_slice(df)
            if len(rth) < 60:
                continue
            pm = premarket_slice(df)
            pdh = prior_day_hlc(ticker, sd)

            # walk-forward calib dict for this day (built from PAST days only)
            calib: Dict[str, Dict] = {}
            for (tk, lt), dq in samples.items():
                if tk != ticker:
                    continue
                qq = rolling_quantiles(list(dq))
                outs = outcomes[(tk, lt)]
                wins, losses = outs.count("win"), outs.count("loss")
                calib[lt] = {
                    "q50": qq[0] if qq else _C["default_q50"],
                    "q90": qq[1] if qq else _C["default_q90"],
                    "respect_rate": wins / (wins + losses)
                    if (wins + losses) >= 5 else None,
                    "n_samples": len(dq),
                }

            # ── simulate the session on 1-min closes ────────────────────────
            zones_active: Dict[str, Dict] = {}
            prev_price = None
            # zone build at 09:40 using truncated data, refreshed every 30 min
            for i in range(10, len(rth)):
                sub = rth.iloc[: i + 1]
                price = float(sub["close"].iloc[-1])
                if i == 10 or i % 30 == 0:
                    atr = compute_atr(resample_5m(sub))
                    refs = reference_levels(ticker, price, sub, pm, pdh)
                    for z in build_zones(ticker, price, atr, refs, calib):
                        if z.direction not in zones_active or \
                                zones_active[z.direction]["dead"]:
                            zones_active[z.direction] = {"zone": z, "dead": False,
                                                         "touched": False}
                for side, zs in zones_active.items():
                    z = zs["zone"]
                    if zs["dead"] or zs["touched"]:
                        continue
                    long_ = side == "long"
                    inz = z.zone_bottom <= price <= z.zone_top
                    outside = prev_price is not None and \
                        (prev_price > z.zone_top if long_
                         else prev_price < z.zone_bottom)
                    if inz and outside:
                        zs["touched"] = True
                        after = rth.iloc[i + 1:]
                        up = z.target1 if long_ else z.stop
                        dn = z.stop if long_ else z.target1
                        oc, mins, mfe, mae = triple_barrier(after, price, up, dn)
                        if not long_ and oc in ("win", "loss"):
                            oc = "win" if oc == "loss" else "loss"
                        risk = abs(price - z.stop) or 1e-9

                        # Point-in-time alert confidence — heuristic in cold-start,
                        # exactly as the live bot would have scored this touch.
                        q50 = (calib.get(z.level_type) or {}).get("q50") \
                            or _C["default_q50"]
                        tail = sub.iloc[-10:]
                        if long_:
                            depth = max(0.0, (z.level - float(tail["low"].min())) / z.level) \
                                if not tail.empty else 0.0
                        else:
                            depth = max(0.0, (float(tail["high"].max()) - z.level) / z.level) \
                                if not tail.empty else 0.0
                        vwap = refs.get("VWAP")
                        ev = {
                            "level_type": z.level_type, "direction": side,
                            "sweep_depth": depth, "rvol": compute_rvol(sub),
                            "session_minute": i,
                            "vwap_dist_atr": (price - vwap) / atr if vwap and atr else 0.0,
                            "confluence": z.confluence, "respect_prior": z.respect_rate,
                        }
                        conf = heuristic_score(ev, float(q50))

                        # Realized R exiting at target1 (win), stop (loss), or
                        # scratch on timeout — the honest fill, not max excursion.
                        if oc == "win":
                            realized_r = abs(z.target1 - price) / risk
                        elif oc == "loss":
                            realized_r = -1.0
                        else:
                            realized_r = 0.0

                        results.append({
                            "ticker": ticker, "date": sd, "lt": z.level_type,
                            "dir": side, "outcome": oc,
                            "r": (mfe / risk) if oc == "win"
                                 else (-1.0 if oc == "loss" else mfe / risk - mae / risk),
                            "conf": conf, "realized_r": realized_r,
                        })
                        outcomes[(ticker, z.level_type)].append(oc)
                prev_price = price

            # fold today's overshoots into rolling calibration (AFTER trading)
            price_close = float(rth["close"].iloc[-1])
            refs_full = reference_levels(ticker, price_close, rth, pm, pdh)
            day_samples = measure_overshoots(rth, refs_full)
            for lt, ov in day_samples:
                samples[(ticker, lt)].append(ov)
            if commit:
                store.insert_sweep_samples([
                    {"ticker": ticker, "session_date": sd,
                     "level_type": lt, "overshoot": ov}
                    for lt, ov in day_samples])
        if (si + 1) % 20 == 0:
            print(f"  … {si + 1}/{len(sessions)} sessions")

    report = _report(results, min_conf, equity_start, risk_frac, cost_r)
    if commit:
        _commit_calibration(tickers, samples, outcomes)
        report += "\nCalibration committed to daytrader.db — live bot is seeded."
        print("Calibration committed to daytrader.db — live bot is seeded.")
    return report


def _report(results: List[Dict], min_conf: float = 0.65,
            equity_start: float = 1000.0, risk_frac: float = 0.01,
            cost_r: float = 0.05) -> str:
    """
    Build the analysis report: per-level touches, ALERTED-only success rate
    (with a 95% CI), R expectancy net of costs, and a $-equity simulation.
    """
    import math
    if not results:
        msg = "No zone touches generated — widen dates or check data access."
        print(msg)
        return msg
    df = pd.DataFrame(results)
    L = [f"{'=' * 66}", f"ALL ZONE TOUCHES: {len(df)}"]

    # ── Per-level (all touches, for context) ──
    for (tk, lt), g in df.groupby(["ticker", "lt"]):
        wins = int((g["outcome"] == "win").sum())
        losses = int((g["outcome"] == "loss").sum())
        to = int((g["outcome"] == "timeout").sum())
        wr = wins / (wins + losses) if (wins + losses) else 0.0
        L.append(f"{tk:6s} {lt:9s} n={len(g):4d} win%={wr:5.1%} "
                 f"timeout={to:3d} avgR={g['r'].mean():+.2f}")

    # ── ALERTED only (what the live bot would actually have fired) ──
    a = df[df["conf"] >= min_conf].copy()
    L.append("=" * 66)
    L.append(f"ALERTED SETUPS (confidence ≥ {min_conf:.0%}): "
             f"{len(a)} of {len(df)} touches")
    if len(a):
        wins = int((a["outcome"] == "win").sum())
        losses = int((a["outcome"] == "loss").sum())
        to = int((a["outcome"] == "timeout").sum())
        decided = wins + losses
        wr = wins / decided if decided else 0.0
        ci = 1.96 * math.sqrt(wr * (1 - wr) / decided) if decided else 0.0
        exp_r = float(a["realized_r"].mean())
        L.append(f"  wins={wins}  losses={losses}  timeouts={to}")
        L.append(f"  SUCCESS RATE = {wr:.1%}  (95% CI ±{ci * 100:.1f} pp, "
                 f"n_decided={decided})")
        L.append(f"  avg R/trade  = {exp_r:+.2f}R   net of {cost_r:.2f}R cost "
                 f"= {exp_r - cost_r:+.2f}R")

        # ── $-equity simulation (chronological, compounding, net of costs) ──
        a_sorted = a.sort_values("date")
        equity, peak, maxdd = equity_start, equity_start, 0.0
        for r in a_sorted["realized_r"]:
            equity += risk_frac * equity * (float(r) - cost_r)
            peak = max(peak, equity)
            if peak > 0:
                maxdd = max(maxdd, (peak - equity) / peak)
        ret = (equity / equity_start - 1) * 100
        L.append("-" * 66)
        L.append(f"EQUITY SIM: ${equity_start:,.0f} → ${equity:,.0f} "
                 f"({ret:+.1f}%) over {len(a)} alerted trades")
        L.append(f"  sizing: risk {risk_frac:.1%} of equity/trade, compounding; "
                 f"max drawdown {maxdd * 100:.1f}%")
    else:
        L.append("  Nothing cleared the alert threshold — no trades would fire.")

    # ── Honesty guardrails (validation.md) ──
    L.append("=" * 66)
    L.append("CAVEATS: in-sample walk-forward (one path, not a held-out period); "
             "small n → wide CI (need ~385 decided trades for 55% to separate "
             "from a coin); assumes fills AT the zone with only the stated cost "
             "model; timeouts counted as 0R. A sanity check, not a promise.")
    report = "\n".join(L)
    print(report)
    return report


def _commit_calibration(tickers, samples, outcomes) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for (tk, lt), dq in samples.items():
        qq = rolling_quantiles(list(dq))
        q50, q90 = qq if qq else (_C["default_q50"], _C["default_q90"])
        outs = outcomes[(tk, lt)]
        wins, losses = outs.count("win"), outs.count("loss")
        respect = wins / (wins + losses) if (wins + losses) >= 5 else -1.0
        store.upsert_calibration(tk, lt, round(q50, 6), round(q90, 6),
                                 respect, len(dq), wins + losses, now)


if __name__ == "__main__":
    load_dotenv()
    store.init_db()
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--tickers", nargs="*", default=CONFIG["tickers"])
    ap.add_argument("--commit", action="store_true",
                    help="seed daytrader.db with the resulting calibration")
    ap.add_argument("--min-conf", type=float, default=None,
                    help="alert confidence threshold (default: config value)")
    ap.add_argument("--equity", type=float, default=1000.0,
                    help="starting equity for the $-simulation")
    ap.add_argument("--risk-frac", type=float, default=0.01,
                    help="fraction of equity risked per alerted trade")
    ap.add_argument("--cost-r", type=float, default=0.05,
                    help="round-trip cost per trade in R units")
    args = ap.parse_args()
    run(args.start, args.end, [t.upper() for t in args.tickers], args.commit,
        min_conf=args.min_conf, equity_start=args.equity,
        risk_frac=args.risk_frac, cost_r=args.cost_r)
