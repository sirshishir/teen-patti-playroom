"""
market_data.py — Fetch OHLCV, options chain, and VIX data.
Primary source: Alpaca Data API. Fallback: yfinance.
"""

import logging
import os
import time
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List, Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Module-level cache for S/R zones (populated at 9 AM ET each day)
_sr_zone_cache: Dict[str, List[Dict]] = {}

# Retry settings for Alpaca API calls
_MAX_RETRIES = 3
_RETRY_DELAY = 0.5  # seconds between retries


def _get_alpaca_stock_client():
    """Lazy-load Alpaca StockHistoricalDataClient."""
    from alpaca.data.historical import StockHistoricalDataClient
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    return StockHistoricalDataClient(api_key, secret_key)


def _get_alpaca_option_client():
    """Lazy-load Alpaca OptionHistoricalDataClient."""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    return OptionHistoricalDataClient(api_key, secret_key)


def _get_trading_client():
    """Lazy-load Alpaca TradingClient."""
    from alpaca.trading.client import TradingClient
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    paper = os.getenv("TRADING_MODE", "paper").lower() == "paper"
    return TradingClient(api_key, secret_key, paper=paper)


# ── OHLCV ─────────────────────────────────────────────────────────────────────

def fetch_ohlcv(ticker: str, interval: str = "5Min",
                period_days: int = 5) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV bars for *ticker*.
    interval: Alpaca bar timeframe string e.g. '5Min', '1Day'.
    Tries Alpaca first, falls back to yfinance.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return _fetch_alpaca_bars(ticker, interval, period_days)
        except Exception as exc:
            logger.warning("Alpaca OHLCV attempt %d failed for %s: %s", attempt, ticker, exc)
            time.sleep(_RETRY_DELAY * attempt)

    logger.warning("Falling back to yfinance for %s", ticker)
    try:
        return _fetch_yfinance_bars(ticker, interval, period_days)
    except Exception as exc:
        logger.error("yfinance also failed for %s: %s", ticker, exc)
        return None


def _fetch_alpaca_bars(ticker: str, interval: str, period_days: int) -> pd.DataFrame:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    # Map interval string to Alpaca TimeFrame
    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    tf = tf_map.get(interval, TimeFrame(5, TimeFrameUnit.Minute))

    end = datetime.utcnow()
    start = end - timedelta(days=period_days)

    client = _get_alpaca_stock_client()
    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=tf,
        start=start,
        end=end,
        feed="iex",
    )
    bars = client.get_stock_bars(req)
    df = bars.df
    if df.empty:
        raise ValueError(f"Empty response for {ticker}")
    # Flatten multi-index if present
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(ticker, level=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() for c in df.columns]
    return df


def _fetch_yfinance_bars(ticker: str, interval: str, period_days: int) -> pd.DataFrame:
    yf_interval_map = {
        "1Min": "1m", "5Min": "5m", "15Min": "15m",
        "1Hour": "1h", "1Day": "1d",
    }
    yf_interval = yf_interval_map.get(interval, "5m")
    period_str = f"{period_days}d" if period_days <= 7 else f"{period_days}d"
    df = yf.download(ticker, period=period_str, interval=yf_interval,
                     auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"yfinance returned empty for {ticker}")
    df.columns = [c.lower() for c in df.columns]
    return df


def fetch_daily_ohlcv(ticker: str, lookback_days: int = 30) -> Optional[pd.DataFrame]:
    """Fetch daily bars used for S/R zone calculation."""
    return fetch_ohlcv(ticker, interval="1Day", period_days=lookback_days)


# ── VIX ───────────────────────────────────────────────────────────────────────

def fetch_vix() -> Optional[float]:
    """Return the latest VIX closing value via yfinance."""
    try:
        df = yf.download("^VIX", period="5d", interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception as exc:
        logger.error("Failed to fetch VIX: %s", exc)
        return None


# ── Options Chain ─────────────────────────────────────────────────────────────

def fetch_options_chain(ticker: str, min_dte: int = 14,
                        max_dte: int = 30) -> Optional[pd.DataFrame]:
    """
    Return options chain rows for *ticker* with DTE in [min_dte, max_dte].
    Uses Alpaca options endpoint; falls back to yfinance.
    """
    try:
        return _fetch_alpaca_options(ticker, min_dte, max_dte)
    except Exception as exc:
        logger.warning("Alpaca options chain failed for %s: %s — trying yfinance", ticker, exc)

    try:
        return _fetch_yfinance_options(ticker, min_dte, max_dte)
    except Exception as exc:
        logger.error("All options chain fetches failed for %s: %s", ticker, exc)
        return None


def _fetch_alpaca_options(ticker: str, min_dte: int, max_dte: int) -> pd.DataFrame:
    from alpaca.data.requests import OptionChainRequest

    today = date.today()
    exp_start = (today + timedelta(days=min_dte)).isoformat()
    exp_end = (today + timedelta(days=max_dte)).isoformat()

    client = _get_alpaca_option_client()
    req = OptionChainRequest(
        underlying_symbol=ticker,
        expiration_date_gte=exp_start,
        expiration_date_lte=exp_end,
    )
    chain = client.get_option_chain(req)
    rows = []
    for symbol, snap in chain.items():
        rows.append({
            "symbol": symbol,
            "strike": snap.details.strike_price,
            "expiry": snap.details.expiration_date,
            "option_type": snap.details.option_type.value,
            "bid": snap.latest_quote.bid_price if snap.latest_quote else None,
            "ask": snap.latest_quote.ask_price if snap.latest_quote else None,
            "mid": None,
            "open_interest": snap.greeks.delta if snap.greeks else None,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"Empty options chain from Alpaca for {ticker}")
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df["dte"] = (pd.to_datetime(df["expiry"]) - pd.Timestamp(today)).dt.days
    return df


def _fetch_yfinance_options(ticker: str, min_dte: int, max_dte: int) -> pd.DataFrame:
    t = yf.Ticker(ticker)
    today = date.today()
    expirations = t.options  # tuple of date strings
    frames = []
    for exp_str in expirations:
        exp = date.fromisoformat(exp_str)
        dte = (exp - today).days
        if not (min_dte <= dte <= max_dte):
            continue
        chain = t.option_chain(exp_str)
        for df_part, opt_type in ((chain.calls, "call"), (chain.puts, "put")):
            df_part = df_part.copy()
            df_part["option_type"] = opt_type
            df_part["expiry"] = exp_str
            df_part["dte"] = dte
            df_part["mid"] = (df_part["bid"] + df_part["ask"]) / 2
            frames.append(df_part)
    if not frames:
        raise ValueError(f"No yfinance options found for {ticker} in DTE range")
    return pd.concat(frames, ignore_index=True)


def select_option_contract(chain: pd.DataFrame, direction: str,
                           current_price: float) -> Optional[Dict[str, Any]]:
    """
    Pick the best ATM / 1-strike OTM contract for *direction* ('call'|'put').
    Returns dict with keys: symbol, strike, expiry, dte, premium.
    """
    opt_type = "call" if direction == "call" else "put"
    sub = chain[chain["option_type"] == opt_type].copy()
    if sub.empty:
        return None

    sub["strike_dist"] = (sub["strike"] - current_price).abs()
    # ATM = closest strike; 1-OTM = next farther in the correct direction
    atm = sub.nsmallest(1, "strike_dist").iloc[0]
    result = {
        "symbol": atm.get("symbol", ""),
        "strike": float(atm["strike"]),
        "expiry": str(atm["expiry"]),
        "dte": int(atm["dte"]),
        "premium": float(atm["mid"]) if pd.notna(atm.get("mid")) else 0.0,
    }
    return result


# ── Market Calendar ───────────────────────────────────────────────────────────

def is_market_open_today() -> bool:
    """Check Alpaca market calendar to see if today is a trading day."""
    try:
        client = _get_trading_client()
        today_str = date.today().isoformat()
        calendars = client.get_calendar(filters={"start": today_str, "end": today_str})
        return len(calendars) > 0
    except Exception as exc:
        logger.error("Market calendar check failed: %s", exc)
        # Assume open on failure to avoid missing trades
        return True


def get_next_earnings_date(ticker: str) -> Optional[date]:
    """Return the next earnings date for *ticker* using yfinance."""
    try:
        t = yf.Ticker(ticker)
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
    """Return True if earnings are within *buffer_days* calendar days."""
    next_earnings = get_next_earnings_date(ticker)
    if next_earnings is None:
        return False  # unknown — treat as safe
    days_away = (next_earnings - date.today()).days
    return 0 <= days_away <= buffer_days


# ── S/R Zone Cache ────────────────────────────────────────────────────────────

def cache_sr_zones() -> None:
    """
    Called once at 9:00 AM ET. Pre-computes S/R zones for all watchlist tickers
    and stores in the module-level cache.  indicators.py reads from this cache.
    """
    from core.indicators import detect_support_resistance

    watchlist = ["GOOGL", "MSFT", "TSLA", "AAPL", "SPY"]
    for ticker in watchlist:
        try:
            df = fetch_daily_ohlcv(ticker, lookback_days=30)
            if df is not None and not df.empty:
                zones = detect_support_resistance(df)
                _sr_zone_cache[ticker] = zones
                logger.info("S/R zones cached for %s: %d zones", ticker, len(zones))
            else:
                logger.warning("No daily data for %s — S/R zones not cached", ticker)
        except Exception as exc:
            logger.error("S/R cache error for %s: %s", ticker, exc)
        time.sleep(0.2)  # rate-limit Alpaca calls


def get_cached_sr_zones(ticker: str) -> List[Dict]:
    """Return cached S/R zones for *ticker*; empty list if not yet cached."""
    return _sr_zone_cache.get(ticker, [])
