"""
market_data.py — Fetch OHLCV, options chain, and VIX data.

Broker routing (controlled by BROKER env var):
  "alpaca" (default) — Primary source: Alpaca Data API. Fallback: yfinance.
  "webull"           — Primary source: Webull Developer API. Fallback: yfinance.
                       Alpaca calls are skipped entirely when BROKER=webull.

Daily analysis cache (populated at 9 AM ET):
  Stores market structure, order blocks, liquidity zones, and Fibonacci levels
  for each watchlist ticker so the 5-minute scanner can skip expensive daily-bar
  recomputation on every cycle.
"""

import logging
import os
import time
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Dict, List, Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Module-level daily analysis cache
_analysis_cache: Dict[str, Dict] = {}

_MAX_RETRIES = 3
_RETRY_DELAY = 0.5

# FIX-1: default to SIP (full consolidated tape). Free on the Basic plan as long
# as the request `end` is >= 15 min old (we subtract 16). An Algo Trader Plus
# subscription can flip to real-time SIP by setting ALPACA_FEED=sip-realtime
# (treated as sip but without the 16-min lag) — kept as a simple override here.
_SIP_LAG_MIN = 16


def _get_broker() -> str:
    """Return the active broker name, lower-cased. Defaults to 'alpaca'."""
    return os.getenv("BROKER", "alpaca").lower()


def _alpaca_feed() -> str:
    """Active Alpaca data feed: 'sip' (default) or 'iex' via ALPACA_FEED env."""
    return os.getenv("ALPACA_FEED", "sip").lower()


# Intervals we build by resampling 1-minute SIP bars (FIX-7) so primary and
# fallback emit identical 09:30-anchored RTH candles.
_RESAMPLE_RULE = {"1Hour": "1h", "4Hour": "4h"}


def _get_alpaca_stock_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(
        os.getenv("ALPACA_API_KEY", ""),
        os.getenv("ALPACA_SECRET_KEY", ""),
    )


def _get_alpaca_option_client():
    from alpaca.data.historical.option import OptionHistoricalDataClient
    return OptionHistoricalDataClient(
        os.getenv("ALPACA_API_KEY", ""),
        os.getenv("ALPACA_SECRET_KEY", ""),
    )


def _get_trading_client():
    from alpaca.trading.client import TradingClient
    paper = os.getenv("TRADING_MODE", "paper").lower() == "paper"
    return TradingClient(
        os.getenv("ALPACA_API_KEY", ""),
        os.getenv("ALPACA_SECRET_KEY", ""),
        paper=paper,
    )


# ── OHLCV ─────────────────────────────────────────────────────────────────────

def fetch_ohlcv(ticker: str, interval: str = "5Min",
                period_days: int = 5) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV bars for *ticker*.

    When BROKER=webull: tries Webull first, falls back to yfinance (skips Alpaca).
    When BROKER=alpaca (default): tries Alpaca with retries, falls back to yfinance.
    """
    broker = _get_broker()

    if broker == "webull":
        # ── Webull primary, yfinance fallback ─────────────────────────────────
        try:
            df = _fetch_webull_bars(ticker, interval, period_days)
            if df is not None and not df.empty:
                return df
            raise ValueError("Empty Webull bars")
        except Exception as exc:
            logger.warning(
                "Webull OHLCV failed for %s: %s — falling back to yfinance", ticker, exc
            )
        try:
            return _fetch_yfinance_bars(ticker, interval, period_days)
        except Exception as exc:
            logger.error("yfinance also failed for %s: %s", ticker, exc)
            return None

    else:
        # ── Alpaca primary, yfinance fallback (default) ───────────────────────
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return _fetch_alpaca_bars(ticker, interval, period_days)
            except Exception as exc:
                logger.warning(
                    "Alpaca OHLCV attempt %d failed for %s: %s", attempt, ticker, exc
                )
                time.sleep(_RETRY_DELAY * attempt)

        logger.warning("Falling back to yfinance for %s", ticker)
        try:
            return _fetch_yfinance_bars(ticker, interval, period_days)
        except Exception as exc:
            logger.error("yfinance also failed for %s: %s", ticker, exc)
            return None


def _fetch_webull_bars(ticker: str, interval: str,
                       period_days: int) -> pd.DataFrame:
    """
    Fetch OHLCV bars from the Webull Developer API.

    Supported intervals: "1Hour", "4Hour", "1Day", "1Week".
    Sub-hourly intervals (e.g. "5Min") are not supported by the Webull bar
    endpoint — callers should fall back to yfinance for those.

    Raises ValueError if the result is None or empty.
    """
    from data.webull_client import get_webull_client

    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=period_days)

    client = get_webull_client()
    df = client.get_bars(
        symbol=ticker,
        interval=interval,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    if df is None or df.empty:
        raise ValueError(f"Webull get_bars returned empty for {ticker} {interval}")
    logger.debug("Webull bars fetched: %s %s rows=%d", ticker, interval, len(df))
    return df


def _fetch_alpaca_bars(ticker: str, interval: str, period_days: int,
                       feed: Optional[str] = None) -> pd.DataFrame:
    """
    Fetch native Alpaca bars.

    FIX-1: default feed is SIP (full consolidated tape) — IEX is ~2% of volume
    and its wicks miss the true extremes that sweeps/order blocks depend on.
    FIX-2: adjustment=ALL (splits/dividends) so a corporate action inside the
    lookback window doesn't create phantom gaps.
    FIX-8: tz-aware UTC datetimes (datetime.now(timezone.utc), not utcnow()).

    For 1Hour/4Hour we resample from 1-minute SIP bars (FIX-7) so boundaries
    match the yfinance fallback exactly.
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import Adjustment, DataFeed

    feed = (feed or _alpaca_feed()).lower()

    # Route 1H/4H through the 1-minute SIP resampler for session alignment.
    if interval in _RESAMPLE_RULE:
        from data.bars import resample_rth
        df_1min = _fetch_alpaca_bars(ticker, "1Min", period_days, feed=feed)
        out = resample_rth(df_1min, _RESAMPLE_RULE[interval])
        if out is None or out.empty:
            raise ValueError(f"Empty resampled {interval} for {ticker}")
        return out

    tf_map = {
        "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
        "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
        "1Week": TimeFrame(1,  TimeFrameUnit.Week),
    }
    tf    = tf_map.get(interval, TimeFrame(5, TimeFrameUnit.Minute))
    end   = datetime.now(timezone.utc)
    if feed.startswith("sip") and feed != "sip-realtime":
        end = end - timedelta(minutes=_SIP_LAG_MIN)  # free-tier SIP: end >= 15 min old
    start = end - timedelta(days=period_days)

    data_feed = DataFeed.IEX if feed == "iex" else DataFeed.SIP
    client = _get_alpaca_stock_client()
    req    = StockBarsRequest(symbol_or_symbols=ticker, timeframe=tf,
                               start=start, end=end,
                               feed=data_feed, adjustment=Adjustment.ALL)
    bars   = client.get_stock_bars(req)
    df     = bars.df
    if df.empty:
        raise ValueError(f"Empty response for {ticker}")
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(ticker, level=0)
    df.index   = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() for c in df.columns]
    return df


def _fetch_yfinance_bars(ticker: str, interval: str,
                          period_days: int) -> pd.DataFrame:
    yf_map = {"1Min": "1m", "5Min": "5m", "15Min": "15m", "1Week": "1wk",
              "1Hour": "1h", "1Day": "1d"}
    df = yf.download(ticker, period=f"{period_days}d",
                     interval=yf_map.get(interval, "5m"),
                     auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"yfinance empty for {ticker}")
    df.columns = [c.lower() for c in df.columns]
    # FIX-7: align 1H boundaries to the same 09:30-anchored RTH candles as the
    # Alpaca path, so primary and fallback produce identical swings/OBs/sweeps.
    if interval == "1Hour":
        from data.bars import resample_rth
        df = resample_rth(df, "1h")
        if df is None or df.empty:
            raise ValueError(f"yfinance 1H resample empty for {ticker}")
    return df


def fetch_daily_ohlcv(ticker: str, lookback_days: int = 60) -> Optional[pd.DataFrame]:
    return fetch_ohlcv(ticker, interval="1Day", period_days=lookback_days)


def fetch_weekly_ohlcv(ticker: str, lookback_weeks: int = 52) -> Optional[pd.DataFrame]:
    """Fetch weekly bars for macro bias detection (52-week default = 1 year)."""
    return fetch_ohlcv(ticker, interval="1Week", period_days=lookback_weeks * 7)


def fetch_4h_ohlcv(ticker: str, lookback_days: int = 30) -> Optional[pd.DataFrame]:
    """
    Fetch 4-hour bars for intermediate order block confirmation.

    When BROKER=webull: tries Webull first, falls back to yfinance 1H→4H resample.
    When BROKER=alpaca (default): tries Alpaca native 4H bars, falls back to
    yfinance 1H→4H resample.
    """
    broker = _get_broker()

    if broker == "webull":
        try:
            df = _fetch_webull_bars(ticker, "4Hour", lookback_days)
            if df is not None and not df.empty:
                return df
            raise ValueError("Empty Webull 4H bars")
        except Exception as exc:
            logger.warning(
                "Webull 4H failed for %s: %s — falling back to yfinance resample",
                ticker, exc,
            )
        try:
            return _fetch_yfinance_4h(ticker, lookback_days)
        except Exception as exc:
            logger.error("4H fetch failed entirely for %s: %s", ticker, exc)
            return None

    else:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return _fetch_alpaca_bars(ticker, "4Hour", lookback_days)
            except Exception as exc:
                logger.warning(
                    "Alpaca 4H attempt %d failed for %s: %s", attempt, ticker, exc
                )
                time.sleep(_RETRY_DELAY * attempt)

        logger.warning("Falling back to yfinance 1H→4H resample for %s", ticker)
        try:
            return _fetch_yfinance_4h(ticker, lookback_days)
        except Exception as exc:
            logger.error("4H fetch failed entirely for %s: %s", ticker, exc)
            return None


def _fetch_yfinance_4h(ticker: str, lookback_days: int) -> pd.DataFrame:
    """yfinance 1H download resampled to 4H (yfinance has no native 4H)."""
    from data.bars import resample_rth
    period = min(lookback_days, 59)   # yfinance caps 1H at 60 days
    df = yf.download(ticker, period=f"{period}d", interval="1h",
                     auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"yfinance 1H empty for {ticker}")
    df.columns = [c.lower() for c in df.columns]
    # FIX-7: resample through the shared RTH-anchored factory so 4H boundaries
    # (09:30-anchored) match the Alpaca 1-min→4H path exactly.
    df_4h = resample_rth(df, "4h")
    if df_4h is None or df_4h.empty:
        raise ValueError(f"4H resample empty for {ticker}")
    return df_4h


# ── VIX ───────────────────────────────────────────────────────────────────────

_vix_cache: Dict[str, Any] = {"value": None, "ts": None}
_VIX_CACHE_MAX_AGE = timedelta(hours=6)


def _extract_last_close(df) -> Optional[float]:
    """Robustly pull the latest close, handling yfinance MultiIndex columns."""
    if df is None or df.empty or "Close" not in df:
        return None
    close = df["Close"]
    # Recent yfinance returns MultiIndex columns → df["Close"] is a DataFrame.
    if hasattr(close, "columns") or getattr(close, "ndim", 1) > 1:
        close = close.iloc[:, 0]
    val = float(close.iloc[-1])
    return val if val == val else None   # guard against NaN


def fetch_vix() -> Optional[float]:
    """
    Return the latest VIX close. Retries yfinance, and on failure falls back to
    the last successfully-fetched value if it's < 6h old. Only returns None when
    VIX has been unavailable long enough that the fail-closed gate should trip.
    """
    for attempt in range(1, 4):
        try:
            df = yf.download("^VIX", period="5d", interval="1d",
                             auto_adjust=True, progress=False)
            val = _extract_last_close(df)
            if val is not None:
                _vix_cache["value"] = val
                _vix_cache["ts"] = datetime.now(timezone.utc)
                return val
        except Exception as exc:
            logger.warning("VIX fetch attempt %d failed: %s", attempt, exc)
        time.sleep(0.5 * attempt)

    # Fallback: recent cached value keeps a transient outage from halting trading.
    if _vix_cache["value"] is not None and _vix_cache["ts"] is not None:
        age = datetime.now(timezone.utc) - _vix_cache["ts"]
        if age <= _VIX_CACHE_MAX_AGE:
            logger.warning("VIX fetch failed — using cached %.1f (age %s)",
                           _vix_cache["value"], age)
            return _vix_cache["value"]

    logger.error("VIX unavailable and no fresh cache — gate will fail closed")
    return None


# ── Options Chain ─────────────────────────────────────────────────────────────

def fetch_options_chain(ticker: str, min_dte: int = 14,
                         max_dte: int = 30) -> Optional[pd.DataFrame]:
    """
    Fetch the options chain for *ticker*.

    When BROKER=webull: tries Webull first, falls back to yfinance (skips Alpaca).
    When BROKER=alpaca (default): tries Alpaca first, falls back to yfinance.
    """
    broker = _get_broker()

    if broker == "webull":
        # ── Webull primary, yfinance fallback ─────────────────────────────────
        try:
            df = _fetch_webull_options(ticker, min_dte, max_dte)
            if df is not None and not df.empty:
                return df
            raise ValueError("Empty Webull options chain")
        except Exception as exc:
            logger.warning(
                "Webull options failed for %s: %s — trying yfinance", ticker, exc
            )
        try:
            return _fetch_yfinance_options(ticker, min_dte, max_dte)
        except Exception as exc:
            logger.error("All options fetches failed for %s: %s", ticker, exc)
            return None

    else:
        # ── Alpaca primary, yfinance fallback (default) ───────────────────────
        try:
            return _fetch_alpaca_options(ticker, min_dte, max_dte)
        except Exception as exc:
            logger.warning(
                "Alpaca options failed for %s: %s — trying yfinance", ticker, exc
            )
        try:
            return _fetch_yfinance_options(ticker, min_dte, max_dte)
        except Exception as exc:
            logger.error("All options fetches failed for %s: %s", ticker, exc)
            return None


def _fetch_webull_options(ticker: str, min_dte: int,
                           max_dte: int) -> pd.DataFrame:
    """
    Fetch options chain from the Webull Developer API and filter by DTE.

    Calls get_webull_client().get_option_chain() with an expiry window derived
    from min_dte / max_dte, then filters rows so only contracts within
    [min_dte, max_dte] are returned.

    Raises ValueError if the result is None or empty after filtering.
    """
    from data.webull_client import get_webull_client

    today     = date.today()
    exp_start = (today + timedelta(days=min_dte)).isoformat()
    exp_end   = (today + timedelta(days=max_dte)).isoformat()

    client = get_webull_client()
    df = client.get_option_chain(
        symbol=ticker,
        exp_date_from=exp_start,
        exp_date_to=exp_end,
    )
    if df is None or df.empty:
        raise ValueError(f"Webull get_option_chain returned empty for {ticker}")

    # Filter to requested DTE range (API may return extras)
    if "dte" in df.columns:
        df = df[(df["dte"] >= min_dte) & (df["dte"] <= max_dte)].copy()

    if df.empty:
        raise ValueError(
            f"Webull options for {ticker} empty after DTE filter "
            f"[{min_dte}, {max_dte}]"
        )

    logger.debug(
        "Webull options fetched: %s rows=%d dte=[%d,%d]",
        ticker, len(df), min_dte, max_dte,
    )
    return df


def _fetch_alpaca_options(ticker: str, min_dte: int,
                           max_dte: int) -> pd.DataFrame:
    from alpaca.data.requests import OptionChainRequest
    today     = date.today()
    exp_start = (today + timedelta(days=min_dte)).isoformat()
    exp_end   = (today + timedelta(days=max_dte)).isoformat()
    client    = _get_alpaca_option_client()
    req       = OptionChainRequest(
        underlying_symbol=ticker,
        expiration_date_gte=exp_start,
        expiration_date_lte=exp_end,
    )
    chain = client.get_option_chain(req)
    rows  = []
    for symbol, snap in chain.items():
        rows.append({
            "symbol":      symbol,
            "strike":      snap.details.strike_price,
            "expiry":      snap.details.expiration_date,
            "option_type": snap.details.option_type.value,
            "bid":         snap.latest_quote.bid_price if snap.latest_quote else None,
            "ask":         snap.latest_quote.ask_price if snap.latest_quote else None,
            "mid":         None,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"Empty Alpaca options for {ticker}")
    df["mid"] = (df["bid"] + df["ask"]) / 2
    # FIX-9: keep mid for display; spread_pct gates tradeability, ask is the fill.
    df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"]
    df["dte"] = (pd.to_datetime(df["expiry"]) - pd.Timestamp(date.today())).dt.days
    return df


def _fetch_yfinance_options(ticker: str, min_dte: int,
                             max_dte: int) -> pd.DataFrame:
    today  = date.today()
    t      = yf.Ticker(ticker)
    frames = []
    for exp_str in t.options:
        dte = (date.fromisoformat(exp_str) - today).days
        if not (min_dte <= dte <= max_dte):
            continue
        chain = t.option_chain(exp_str)
        for df_part, opt_type in ((chain.calls, "call"), (chain.puts, "put")):
            df_part             = df_part.copy()
            df_part["option_type"] = opt_type
            df_part["expiry"]   = exp_str
            df_part["dte"]      = dte
            df_part["mid"]      = (df_part["bid"] + df_part["ask"]) / 2
            df_part["spread_pct"] = (df_part["ask"] - df_part["bid"]) / df_part["mid"]
            frames.append(df_part)
    if not frames:
        raise ValueError(f"No yfinance options for {ticker}")
    return pd.concat(frames, ignore_index=True)


def select_option_contract(chain: pd.DataFrame, direction: str,
                            current_price: float,
                            max_spread_pct: float = 0.08) -> Optional[Dict[str, Any]]:
    """
    Pick the ATM contract, rejecting illiquid (wide-spread) options.

    FIX-9: entry premium is the ASK (what you actually pay), not the mid — mid
    flatters every fill by half the spread. Contracts with
    spread_pct > max_spread_pct are skipped.
    """
    opt_type = "call" if direction == "call" else "put"
    sub = chain[chain["option_type"] == opt_type].copy()
    if sub.empty:
        return None

    if "spread_pct" not in sub.columns:
        sub["spread_pct"] = (sub["ask"] - sub["bid"]) / sub["mid"]

    tradeable = sub[sub["spread_pct"].notna() & (sub["spread_pct"] <= max_spread_pct)]
    if tradeable.empty:
        best_spread = sub["spread_pct"].min()
        logger.warning(
            "No %s contract within max_spread_pct=%.2f (tightest %.2f) — skipping",
            opt_type, max_spread_pct,
            best_spread if pd.notna(best_spread) else float("nan"),
        )
        return None

    tradeable = tradeable.copy()
    tradeable["strike_dist"] = (tradeable["strike"] - current_price).abs()
    atm = tradeable.nsmallest(1, "strike_dist").iloc[0]

    mid = float(atm["mid"]) if pd.notna(atm.get("mid")) else 0.0
    ask = float(atm["ask"]) if pd.notna(atm.get("ask")) else mid
    return {
        "symbol":     atm.get("symbol", ""),
        "strike":     float(atm["strike"]),
        "expiry":     str(atm["expiry"]),
        "dte":        int(atm["dte"]),
        "premium":    ask,                       # FIX-9: fill at the ask
        "mid":        mid,                        # kept for display
        "ask":        ask,
        "spread_pct": float(atm["spread_pct"]) if pd.notna(atm.get("spread_pct")) else None,
    }


# ── Market Calendar ───────────────────────────────────────────────────────────

def is_market_open_today() -> bool:
    try:
        from alpaca.trading.requests import GetCalendarRequest
        client    = _get_trading_client()
        today     = date.today()
        req       = GetCalendarRequest(start=today, end=today)
        calendars = client.get_calendar(req)
        return len(calendars) > 0
    except Exception as exc:
        logger.error("Market calendar check failed: %s", exc)
        return True


def get_next_earnings_date(ticker: str) -> Optional[date]:
    try:
        t   = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None or "Earnings Date" not in cal:
            return None
        raw = cal["Earnings Date"]
        if hasattr(raw, "__iter__") and not isinstance(raw, str):
            raw = list(raw)
            if raw:
                raw = raw[0]
        if isinstance(raw, (datetime, date)):
            return raw.date() if isinstance(raw, datetime) else raw
        return None
    except Exception as exc:
        logger.warning("Could not fetch earnings for %s: %s", ticker, exc)
        return None


def earnings_within_days(ticker: str, buffer_days: int) -> bool:
    nxt = get_next_earnings_date(ticker)
    if nxt is None:
        return False
    return 0 <= (nxt - date.today()).days <= buffer_days


# ── Daily Analysis Cache ──────────────────────────────────────────────────────

def build_ticker_analysis(ticker: str) -> Optional[Dict]:
    """
    Build the full multi-timeframe SMC analysis for a single ticker:
      Weekly  → macro bias (trend direction + 20-week SMA)
      Daily   → market structure, order blocks, liquidity zones, Fibonacci
      4-Hour  → intermediate order blocks for entry confluence

    Returns the analysis dict, or None if daily data is unavailable. This does
    live network fetches every call — used both by the 9 AM cache job and by
    on-demand commands (e.g. /analysis) that need fresh, un-cached data.
    """
    from core.indicators import (
        detect_swing_points, detect_market_structure,
        detect_liquidity_zones, detect_order_blocks,
        compute_fibonacci_levels, compute_atr,
        detect_weekly_bias,
    )

    # ── Weekly bias ────────────────────────────────────────────────────────
    df_weekly   = fetch_weekly_ohlcv(ticker, lookback_weeks=52)
    weekly_bias = (detect_weekly_bias(df_weekly)
                   if df_weekly is not None and not df_weekly.empty
                   else {"trend": "ranging"})
    time.sleep(0.2)

    # ── Daily structure ────────────────────────────────────────────────────
    df_daily = fetch_daily_ohlcv(ticker, lookback_days=60)
    if df_daily is None or df_daily.empty:
        logger.warning("No daily data for %s — analysis unavailable", ticker)
        return None

    sh_idx, sl_idx  = detect_swing_points(df_daily, order=3)
    market_struct   = detect_market_structure(df_daily, sh_idx, sl_idx)
    liquidity_zones = detect_liquidity_zones(df_daily)
    atr_daily       = compute_atr(df_daily, period=14)
    order_blocks    = detect_order_blocks(df_daily, sh_idx, sl_idx, atr_daily)
    fib             = compute_fibonacci_levels(df_daily, sh_idx, sl_idx, market_struct)
    time.sleep(0.2)

    # ── 4-Hour order blocks ──────────────────────────────────────────────────
    df_4h  = fetch_4h_ohlcv(ticker, lookback_days=30)
    ob_4h  = []
    if df_4h is not None and len(df_4h) >= 10:
        sh_4h, sl_4h = detect_swing_points(df_4h, order=2)
        atr_4h       = compute_atr(df_4h, period=14)
        ob_4h        = detect_order_blocks(df_4h, sh_4h, sl_4h, atr_4h)
    time.sleep(0.2)

    return {
        "weekly_bias":      weekly_bias,
        "market_structure": market_struct,
        "order_blocks":     order_blocks,
        "liquidity_zones":  liquidity_zones,
        "fibonacci":        fib,
        "ob_4h":            ob_4h,
    }


def cache_sr_zones() -> None:
    """
    Called once at 9:00 AM ET (scheduler-compatible name kept).

    Builds and caches the full multi-timeframe SMC analysis for every ticker in
    the (dynamic) watchlist so the 30-minute scanner can reuse it cheaply.
    """
    from data import database as db

    for ticker in db.get_watchlist():
        try:
            analysis = build_ticker_analysis(ticker)
            if analysis is None:
                logger.warning("No analysis for %s — cache skipped", ticker)
                continue
            _analysis_cache[ticker] = analysis
            logger.info(
                "Cache built for %s: weekly=%s daily=%s "
                "daily_OBs=%d 4H_OBs=%d liq_zones=%d",
                ticker,
                analysis["weekly_bias"].get("trend"),
                analysis["market_structure"].get("trend"),
                len(analysis["order_blocks"]), len(analysis["ob_4h"]),
                len(analysis["liquidity_zones"]),
            )
        except Exception as exc:
            logger.error("Cache error for %s: %s", ticker, exc)


def get_cached_analysis(ticker: str) -> Dict:
    """Return the daily analysis cache for *ticker*; empty dict if not cached."""
    return _analysis_cache.get(ticker, {})


# Legacy alias — kept so any stale import in tests still resolves
def get_cached_sr_zones(ticker: str) -> List[Dict]:
    """Deprecated: use get_cached_analysis(). Returns order_blocks list."""
    return _analysis_cache.get(ticker, {}).get("order_blocks", [])
