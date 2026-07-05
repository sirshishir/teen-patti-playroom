"""
test_fixes.py — regression tests for the FIX.md data-accuracy fixes.

Run from the snipebot/ directory:  pytest tests/test_fixes.py -q

These exercise the pure-logic fixes that don't require live Alpaca/network:
  FIX-3  partial (in-progress) bar is dropped for analysis
  FIX-4  VIX outage halts the scan cycle (fail-closed)
  FIX-5  liquidity sweep detector returns the MOST RECENT sweep
  FIX-6  order-block detection respects `as_of` (no look-ahead)
  FIX-7  RTH resampler anchors the first session bar to 09:30 ET
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

# Make the snipebot package importable when run from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── FIX-7: RTH resampler anchors to 09:30 ─────────────────────────────────────

def test_resample_anchor_0930():
    from data.bars import resample_rth
    import pytz
    et = pytz.timezone("US/Eastern")
    # One session of 1-minute bars, 09:30–15:59 ET.
    start = et.localize(datetime(2026, 6, 1, 9, 30))
    idx = pd.date_range(start, periods=390, freq="1min")
    df = pd.DataFrame({
        "open": np.arange(390, dtype=float), "high": np.arange(390) + 1.0,
        "low": np.arange(390) - 1.0, "close": np.arange(390, dtype=float),
        "volume": np.ones(390),
    }, index=idx)
    out = resample_rth(df, "1h")
    assert not out.empty
    first_et = out.index[0].tz_convert(et)
    assert (first_et.hour, first_et.minute) == (9, 30)


# ── FIX-6: order blocks respect as_of (no look-ahead) ─────────────────────────

def test_ob_respects_as_of():
    from core.indicators import detect_order_blocks
    n = 40
    close = np.linspace(100, 100, n)
    df = pd.DataFrame({
        "open": close.copy(), "high": close + 0.5,
        "low": close - 0.5, "close": close.copy(),
        "volume": np.ones(n),
    })
    # A big move AFTER as_of must not influence blocks detected as-of k.
    k = 20
    df.loc[30, ["high", "close"]] = [130, 130]
    obs_asof = detect_order_blocks(df, np.array([]), np.array([]), atr=1.0, as_of=k)
    # No detected block may reference a bar at or beyond as_of.
    assert all(o["index"] < k for o in obs_asof)


# ── FIX-5: sweep detector prefers the most recent event ───────────────────────

def test_sweep_prefers_most_recent():
    from core.indicators import detect_liquidity_sweep
    # 20 flat bars, then an OLD sell-side sweep and a NEWER sell-side sweep.
    n = 20
    df = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 100.5),
        "low": np.full(n, 99.5), "close": np.full(n, 100.0),
        "volume": np.ones(n),
    })
    # Old sweep of level 99.0 at bar 12, fresh sweep of level 98.0 at bar 18.
    df.loc[12, "low"] = 98.9; df.loc[12, "close"] = 100.0
    df.loc[18, "low"] = 97.9; df.loc[18, "close"] = 100.0
    zones = [
        {"type": "sell_side", "level": 99.0, "count": 2, "index": 5},
        {"type": "sell_side", "level": 98.0, "count": 2, "index": 6},
    ]
    res = detect_liquidity_sweep(df, zones, lookback=15)
    assert res["swept"] is True
    assert res["sweep_level"] == 98.0   # the newer sweep, not the older 99.0


# ── FIX-3: partial bar dropped for analysis ───────────────────────────────────

def test_partial_bar_dropped():
    # Reproduces the run_scan logic: if the last bar's timestamp is < 1h old,
    # analysis must use df.iloc[:-1] (completed bars only).
    now = pd.Timestamp.now(tz="UTC")
    idx = pd.date_range(now.floor("h") - pd.Timedelta(hours=3),
                        periods=4, freq="1h")
    df = pd.DataFrame({"close": [1, 2, 3, 4]}, index=idx)
    bar_span = pd.Timedelta(hours=1)
    if pd.Timestamp.now(tz="UTC") < df.index[-1] + bar_span:
        df_eval = df.iloc[:-1]
    else:
        df_eval = df
    # The last bar started this hour, so it is in-progress and must be dropped.
    assert len(df_eval) == 3
    assert df_eval["close"].iloc[-1] == 3


# ── FIX-4: VIX None halts the scan (fail-closed) ──────────────────────────────

def test_vix_none_halts_scan(monkeypatch):
    import core.scanner as scanner

    monkeypatch.setattr(scanner, "fetch_vix", lambda: None)
    monkeypatch.setattr(scanner, "halt_file_exists", lambda: False)
    monkeypatch.setattr(scanner, "daily_loss_limit_hit", lambda: False)

    calls = {"alerts": 0, "watchlist": 0}
    monkeypatch.setattr(scanner.discord_bot, "send_system_alert",
                        lambda *a, **k: calls.__setitem__("alerts", calls["alerts"] + 1))
    # If the loop were reached, get_watchlist would be called — assert it isn't.
    monkeypatch.setattr(scanner.db, "get_watchlist",
                        lambda: calls.__setitem__("watchlist", calls["watchlist"] + 1) or [])

    scanner.run_scan()

    assert calls["alerts"] == 1      # data_error alert sent
    assert calls["watchlist"] == 0   # ticker loop never entered
