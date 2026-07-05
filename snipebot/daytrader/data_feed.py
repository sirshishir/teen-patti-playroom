"""data_feed.py — hybrid SIP/IEX minute-bar feed (free tier).

Strategy
--------
Free-tier rules: SIP (100% of tape) is queryable when the request `end` is
>= 15 minutes old; IEX (~2% of tape) is real-time. So every fetch is stitched:

    [premarket 04:00 ET ........ now-16min]  -> SIP   (exact wicks/volume)
    (now-16min ................. now]        -> IEX   (fresh but thin)

Rows that exist in both windows prefer SIP. Any HOD/level set more than
16 minutes ago is therefore consolidated-tape exact; only the newest few
minutes rely on IEX and self-correct on the next tick.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

from daytrader.settings import CONFIG, ET

logger = logging.getLogger(__name__)

_SIP_DELAY = timedelta(minutes=int(CONFIG["data"]["sip_delay_minutes"]))


def _client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(
        os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", ""),
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_et() -> datetime:
    return now_utc().astimezone(ET)


def session_date_str(dt_et: Optional[datetime] = None) -> str:
    return (dt_et or now_et()).strftime("%Y-%m-%d")


def _fetch(tickers: List[str], start: datetime, end: datetime,
           feed: str, timeframe=None) -> Dict[str, pd.DataFrame]:
    """One batched bars request → {ticker: df}. Empty dict on failure."""
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    if end <= start:
        return {}
    req = StockBarsRequest(
        symbol_or_symbols=list(tickers),
        timeframe=timeframe or TimeFrame.Minute,
        start=start, end=end,
        feed=DataFeed.SIP if feed == "sip" else DataFeed.IEX,
        adjustment=Adjustment.ALL,
        limit=10000,
    )
    try:
        df = _client().get_stock_bars(req).df
    except Exception as exc:
        logger.warning("bars fetch failed (%s %s→%s): %s", feed, start, end, exc)
        return {}
    if df is None or df.empty:
        return {}
    out: Dict[str, pd.DataFrame] = {}
    if isinstance(df.index, pd.MultiIndex):
        for t in tickers:
            if t in df.index.get_level_values(0):
                sub = df.xs(t, level=0).copy()
                sub.index = pd.to_datetime(sub.index, utc=True)
                out[t] = sub
    else:
        sub = df.copy()
        sub.index = pd.to_datetime(sub.index, utc=True)
        out[tickers[0]] = sub
    for t, sub in out.items():
        sub.columns = [c.lower() for c in sub.columns]
    return out


def get_session_frames(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """Full session (premarket 04:00 ET → now) 1-min frame per ticker,
    SIP for everything older than the delay window, IEX for the tail."""
    n_et = now_et()
    pm_h, pm_m = (int(x) for x in CONFIG["data"]["premarket_start"].split(":"))
    session_start = ET.localize(
        datetime(n_et.year, n_et.month, n_et.day, pm_h, pm_m)
    ).astimezone(timezone.utc)
    n_utc = now_utc()
    sip_end = n_utc - _SIP_DELAY

    frames: Dict[str, pd.DataFrame] = {}
    sip = _fetch(tickers, session_start, sip_end, "sip") if sip_end > session_start else {}
    iex = _fetch(tickers, max(session_start, sip_end), n_utc, "iex")

    for t in tickers:
        parts = [p for p in (sip.get(t), iex.get(t)) if p is not None and not p.empty]
        if not parts:
            continue
        df = pd.concat(parts)
        df = df[~df.index.duplicated(keep="first")].sort_index()  # SIP wins overlaps
        frames[t] = df
    return frames


def get_day_frame_sip(ticker: str, session_date: str) -> Optional[pd.DataFrame]:
    """Full historical session as pure SIP 1-min bars (for nightly jobs /
    backtests — always >15 min old, so free)."""
    d = datetime.strptime(session_date, "%Y-%m-%d")
    start = ET.localize(d.replace(hour=4, minute=0)).astimezone(timezone.utc)
    end = ET.localize(d.replace(hour=20, minute=0)).astimezone(timezone.utc)
    end = min(end, now_utc() - _SIP_DELAY)
    got = _fetch([ticker], start, end, "sip")
    return got.get(ticker)


def prior_day_hlc(ticker: str, before_date: Optional[str] = None
                  ) -> Optional[Tuple[float, float, float]]:
    """(high, low, close) of the last completed session strictly before
    `before_date` (default: today). SIP daily bars, split/div adjusted."""
    from alpaca.data.timeframe import TimeFrame
    end = now_utc() - _SIP_DELAY
    if before_date:
        d = ET.localize(datetime.strptime(before_date, "%Y-%m-%d")).astimezone(timezone.utc)
        end = min(end, d)
    got = _fetch([ticker], end - timedelta(days=10), end, "sip",
                 timeframe=TimeFrame.Day)
    df = got.get(ticker)
    if df is None or df.empty:
        return None
    ref = (before_date or session_date_str())
    df = df[df.index.tz_convert(ET).strftime("%Y-%m-%d") < ref]
    if df.empty:
        return None
    last = df.iloc[-1]
    return float(last["high"]), float(last["low"]), float(last["close"])


# ── session slicing helpers ───────────────────────────────────────────────────

def to_et(df: pd.DataFrame) -> pd.DataFrame:
    return df.tz_convert(ET)


def rth_slice(df: pd.DataFrame) -> pd.DataFrame:
    return to_et(df).between_time("09:30", "15:59")


def premarket_slice(df: pd.DataFrame) -> pd.DataFrame:
    return to_et(df).between_time("04:00", "09:29")


def cumulative_vwap(df_rth: pd.DataFrame) -> Optional[float]:
    if df_rth.empty or df_rth["volume"].sum() == 0:
        return None
    tp = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    return float((tp * df_rth["volume"]).sum() / df_rth["volume"].sum())


def is_market_open_today() -> bool:
    """Weekday + Alpaca trading calendar when available. Fail-open with a log
    (alerts-only bot — worst case is a quiet false alert on a holiday)."""
    if now_et().weekday() >= 5:
        return False
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetCalendarRequest
        tc = TradingClient(os.getenv("ALPACA_API_KEY", ""),
                           os.getenv("ALPACA_SECRET_KEY", ""), paper=True)
        today = now_et().date()
        cal = tc.get_calendar(GetCalendarRequest(start=today, end=today))
        return len(cal) > 0
    except Exception as exc:
        logger.warning("calendar check failed (%s) — assuming open", exc)
        return True
