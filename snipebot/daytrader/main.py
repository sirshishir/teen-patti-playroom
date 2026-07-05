"""main.py — daytrader entrypoint.

Run from the snipebot directory:  python -m daytrader.main

Jobs (ET):
  09:15        premarket battle plan          (PD/PM levels, open provisional)
  09:40        confirmed plan                 (true SIP session open known)
  09:30–16:00  tick every 60 s                (state machine → event alerts)
  16:05        recap
  18:30        nightly calibration            (quantiles + triple-barrier labels)
  Sun 19:00    weekly scorer retrain

Alerts-only: this process NEVER places orders.
"""

import logging
import time
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from daytrader import alerts, calibrate, scorer, store
from daytrader.data_feed import (get_session_frames, is_market_open_today,
                                 now_et, premarket_slice, prior_day_hlc,
                                 rth_slice, session_date_str)
from daytrader.levels_engine import (Zone, build_zones, compute_atr,
                                     compute_rvol, levels_table,
                                     reference_levels, render_table,
                                     resample_5m)
from daytrader.settings import CONFIG, ET

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("daytrader")

_L = CONFIG["levels"]
TICKERS = CONFIG["tickers"]

# runtime state: {ticker: {"long": zstate|None, "short": zstate|None, ...}}
STATE: Dict[str, Dict] = {}
_PD_CACHE: Dict[str, tuple] = {}
_TICK_N = 0


def _zstate(zone: Zone) -> Dict:
    return {"zone": zone, "status": "armed", "entries": 0,
            "entered": False, "t1": False, "t2": False}


def _reset_day() -> None:
    STATE.clear()
    _PD_CACHE.clear()


def _pd_hlc(ticker: str) -> Optional[tuple]:
    if ticker not in _PD_CACHE:
        _PD_CACHE[ticker] = prior_day_hlc(ticker)
    return _PD_CACHE[ticker]


def _build_context(ticker: str, frame):
    rth = rth_slice(frame)
    pm = premarket_slice(frame)
    price = float(frame["close"].iloc[-1])
    atr = compute_atr(resample_5m(rth)) if not rth.empty else 0.0
    refs = reference_levels(ticker, price, rth, pm, _pd_hlc(ticker))
    return rth, pm, price, atr, refs


# ── plans ─────────────────────────────────────────────────────────────────────

def send_plans(version: str = "") -> None:
    if not is_market_open_today():
        return
    frames = get_session_frames(TICKERS)
    for ticker in TICKERS:
        frame = frames.get(ticker)
        if frame is None or frame.empty:
            continue
        rth, pm, price, atr, refs = _build_context(ticker, frame)
        calib = calibrate.load_calibration(ticker)
        zones = build_zones(ticker, price, atr if atr else price * 0.003,
                            refs, calib)
        long_z = next((z for z in zones if z.direction == "long"), None)
        bias = "LONG (above VWAP/open)" if refs.get("VWAP", 0) and \
            price >= refs.get("VWAP", price) and price >= refs.get("OPEN", price) \
            else "SHORT / defensive (below VWAP or open)"
        table = render_table(levels_table(price, refs, long_z))
        alerts.send_plan(ticker, table, bias, version)
        st = STATE.setdefault(ticker, {"long": None, "short": None})
        for z in zones:
            slot = st.get(z.direction)
            if slot is None or slot["status"] == "dead":
                st[z.direction] = _zstate(z)


# ── intraday state machine ────────────────────────────────────────────────────

def _handle_zone(ticker: str, side: str, st: Dict, price: float,
                 prev: Optional[float], rth, atr: float,
                 refs: Dict, calib: Dict) -> None:
    zs = st.get(side)
    if not zs or zs["status"] == "dead":
        return
    z: Zone = zs["zone"]
    is_long = side == "long"
    in_zone = (z.zone_bottom <= price <= z.zone_top) if is_long else \
              (z.zone_bottom <= price <= z.zone_top)
    last_close = float(rth["close"].iloc[-1]) if not rth.empty else price

    # invalidation — 1-min close beyond stop
    if (is_long and last_close < z.stop) or (not is_long and last_close > z.stop):
        alerts.send_invalidation(ticker, z, price)
        zs["status"] = "dead"
        return

    # touch → score → alert + record
    was_outside = prev is not None and (prev > z.zone_top if is_long
                                        else prev < z.zone_bottom)
    if zs["status"] == "armed" and in_zone and was_outside and \
            zs["entries"] < int(_L["max_entries_per_zone"]):
        tail = rth.iloc[-10:] if not rth.empty else rth
        if is_long:
            depth = max(0.0, (z.level - float(tail["low"].min())) / z.level) \
                if not tail.empty else 0.0
        else:
            depth = max(0.0, (float(tail["high"].max()) - z.level) / z.level) \
                if not tail.empty else 0.0
        vwap = refs.get("VWAP")
        minute = int((now_et() - now_et().replace(hour=9, minute=30,
                                                  second=0)).total_seconds() // 60)
        ev = {
            "ticker": ticker, "session_date": session_date_str(),
            "level_type": z.level_type, "direction": side,
            "level": z.level, "zone_top": z.zone_top,
            "zone_bottom": z.zone_bottom, "stop": z.stop,
            "target1": z.target1, "target2": z.target2,
            "touch_time": rth.index[-1].isoformat() if not rth.empty else None,
            "touch_price": price, "sweep_depth": round(depth, 6),
            "rvol": compute_rvol(rth), "session_minute": minute,
            "vwap_dist_atr": round((price - vwap) / atr, 3) if vwap and atr else 0.0,
            "confluence": z.confluence,
            "respect_prior": z.respect_rate,
        }
        row = calib.get(z.level_type) or {}
        q50 = row.get("q50") or CONFIG["calibration"]["default_q50"]
        conf = scorer.get_confidence(ev, float(q50))
        ev["confidence"] = conf
        store.insert_zone_event(ev)          # every touch is a training sample
        zs["entries"] += 1
        zs["entered"] = True
        zs["status"] = "in_zone"
        if conf >= float(CONFIG["scorer"]["min_confidence_alert"]):
            alerts.send_zone_entry(ticker, z, price, conf, depth, zs["entries"])
        else:
            logger.info("%s %s touch suppressed (conf %.2f)", ticker,
                        z.level_type, conf)

    # targets
    if zs["entered"]:
        hit1 = price >= z.target1 if is_long else price <= z.target1
        hit2 = price >= z.target2 if is_long else price <= z.target2
        if hit1 and not zs["t1"]:
            zs["t1"] = True
            alerts.send_target_hit(ticker, z, 1, price)
        if hit2 and not zs["t2"]:
            zs["t2"] = True
            alerts.send_target_hit(ticker, z, 2, price)
            zs["status"] = "dead"

    # re-arm hysteresis
    rearm = float(_L["rearm_atr"]) * atr
    left = (price > z.zone_top + rearm) if is_long else (price < z.zone_bottom - rearm)
    if zs["status"] == "in_zone" and left and \
            zs["entries"] < int(_L["max_entries_per_zone"]):
        zs["status"] = "armed"


def tick() -> None:
    global _TICK_N
    n = now_et()
    if n.weekday() >= 5 or not (n.hour, n.minute) >= (9, 30) or n.hour >= 16:
        return
    if _TICK_N == 0 and not is_market_open_today():
        return
    _TICK_N += 1
    frames = get_session_frames(TICKERS)
    for ticker in TICKERS:
        frame = frames.get(ticker)
        if frame is None or frame.empty:
            continue
        rth, pm, price, atr, refs = _build_context(ticker, frame)
        if rth.empty or atr <= 0:
            continue
        calib = calibrate.load_calibration(ticker)
        st = STATE.setdefault(ticker, {"long": None, "short": None,
                                       "prev_price": None})
        # refresh zones every 5 ticks; keep in-flight zones sticky
        if _TICK_N % 5 == 1:
            for z in build_zones(ticker, price, atr, refs, calib):
                slot = st.get(z.direction)
                if slot is None or slot["status"] == "dead" or \
                        (slot["status"] == "armed" and not slot["entered"]):
                    st[z.direction] = _zstate(z)
        prev = st.get("prev_price")
        for side in ("long", "short"):
            _handle_zone(ticker, side, st, price, prev, rth, atr, refs, calib)
        st["prev_price"] = price


# ── EOD / nightly / weekly ────────────────────────────────────────────────────

def recap() -> None:
    for ticker in TICKERS:
        alerts.send_recap(ticker, store.events_for_session(session_date_str()))


def nightly() -> None:
    stats = calibrate.run_nightly()
    alerts.send_system(
        f"🌙 Calibration done — {stats['samples']} sweep samples, "
        f"{stats['labeled']} events labeled. Zones will use fresh quantiles "
        f"tomorrow.")
    _reset_day()


def weekly_retrain() -> None:
    acc = scorer.train_model()
    if acc is not None:
        alerts.send_system(f"🧠 Scorer retrained — holdout accuracy {acc:.1%}.")


def _run_analyst() -> None:
    from daytrader import analyst        # lazy: bot runs fine without an API key
    analyst.run_weekly()


def run() -> None:
    load_dotenv()
    store.init_db()
    a = CONFIG["alerts"]
    sched = BackgroundScheduler(timezone=ET)
    h1, m1 = a["premarket_plan_time"].split(":")
    h2, m2 = a["confirmed_plan_time"].split(":")
    h3, m3 = a["eod_recap_time"].split(":")
    h4, m4 = a["nightly_calibration_time"].split(":")
    wd, wt = a["weekly_retrain"]["day"], a["weekly_retrain"]["time"]
    h5, m5 = wt.split(":")

    sched.add_job(send_plans, "cron", day_of_week="mon-fri", hour=int(h1),
                  minute=int(m1), kwargs={"version": ""})
    sched.add_job(send_plans, "cron", day_of_week="mon-fri", hour=int(h2),
                  minute=int(m2), kwargs={"version": ".v2"})
    sched.add_job(tick, "interval", seconds=int(CONFIG["data"]["poll_seconds"]))
    sched.add_job(recap, "cron", day_of_week="mon-fri", hour=int(h3), minute=int(m3))
    sched.add_job(nightly, "cron", day_of_week="mon-fri", hour=int(h4), minute=int(m4))
    sched.add_job(weekly_retrain, "cron", day_of_week=wd, hour=int(h5), minute=int(m5))
    an = CONFIG.get("analyst") or {}
    if an.get("enabled"):
        ah, am = an["time"]["time"].split(":")
        sched.add_job(_run_analyst, "cron", day_of_week=an["time"]["day"],
                      hour=int(ah), minute=int(am))
    sched.start()
    alerts.send_system("✅ daytrader online — alerts only, no orders. "
                       f"Watching: {', '.join(TICKERS)}")
    logger.info("daytrader running; tickers=%s", TICKERS)
    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()


if __name__ == "__main__":
    run()
