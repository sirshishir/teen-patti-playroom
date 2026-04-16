"""
market_data.py — Fetch OHLCV, options chain, and VIX data.
Primary source: Alpaca Data API. Fallback: yfinance.

Daily analysis cache (populated at 9 AM ET):
  Stores market structure, order blocks, liquidity zones, and Fibonacci levels
  for each watchlist ticker so the 5-minute scanner can skip expensive daily-bar
  recomputation on every cycle.
"""

import logging
import os
import time
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List, Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Module-level daily analysis cache
_analysis_cache: Dict[str, Dict] = {}

_MAX_RETRIES = 3
_RETRY_DELAY = 0.5


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
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return _fetch_alpaca_bars(ticker, interval, period_days)
        except Exception as exc:
            logger.warning("Alpaca OHLCV attempt %d failed for %s: %s",
                           attempt, ticker, exc)
            time.sleep(_RETRY_DELAY * attempt)

    logger.warning("Falling back to yfinance for %s", ticker)
    try:
        return _fetch_yfinance_bars(ticker, interval, period_days)
    except Exception as exc:
        logger.error("yfinance also failed for %s: %s", ticker, exc)
        return None


def _fetch_alpaca_bars(ticker: str, interval: str,
                        period_days: int) -> pd.DataFrame:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
        "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1,  TimeFrameUnit.Hour),
        "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
    }
    tf    = tf_map.get(interval, TimeFrame(5, TimeFrameUnit.Minute))
    end   = datetime.utcnow()
    start = end - timedelta(days=period_days)

    client = _get_alpaca_stock_client()
    req    = StockBarsRequest(symbol_or_symbols=ticker, timeframe=tf,
                               start=start, end=end, feed="iex")
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
    yf_map = {"1Min": "1m", "5Min": "5m", "15Min": "15m",
              "1Hour": "1h", "1Day": "1d"}
    df = yf.download(ticker, period=f"{period_days}d",
                     interval=yf_map.get(interval, "5m"),
                     auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"yfinance empty for {ticker}")
    df.columns = [c.lower() for c in df.columns]
    return df


def fetch_daily_ohlcv(ticker: str, lookback_days: int = 60) -> Optional[pd.DataFrame]:
    return fetch_ohlcv(ticker, interval="1Day", period_days=lookback_days)


# ── VIX ───────────────────────────────────────────────────────────────────────

def fetch_vix() -> Optional[float]:
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
    try:
        return _fetch_alpaca_options(ticker, min_dte, max_dte)
    except Exception as exc:
        logger.warning("Alpaca options failed for %s: %s — trying yfinance", ticker, exc)
    try:
        return _fetch_yfinance_options(ticker, min_dte, max_dte)
    except Exception as exc:
        logger.error("All options fetches failed for %s: %s", ticker, exc)
        return None


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
            frames.append(df_part)
    if not frames:
        raise ValueError(f"No yfinance options for {ticker}")
    return pd.concat(frames, ignore_index=True)


def select_option_contract(chain: pd.DataFrame, direction: str,
                            current_price: float) -> Optional[Dict[str, Any]]:
    opt_type = "call" if direction == "call" else "put"
    sub = chain[chain["option_type"] == opt_type].copy()
    if sub.empty:
        return None
    sub["strike_dist"] = (sub["strike"] - current_price).abs()
    atm = sub.nsmallest(1, "strike_dist").iloc[0]
    return {
        "symbol":  atm.get("symbol", ""),
        "strike":  float(atm["strike"]),
        "expiry":  str(atm["expiry"]),
        "dte":     int(atm["dte"]),
        "premium": float(atm["mid"]) if pd.notna(atm.get("mid")) else 0.0,
    }


# ── Market Calendar ───────────────────────────────────────────────────────────

def is_market_open_today() -> bool:
    try:
        client    = _get_trading_client()
        today_str = date.today().isoformat()
        calendars = client.get_calendar(filters={"start": today_str, "end": today_str})
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

def cache_sr_zones() -> None:
    """
    Called once at 9:00 AM ET (scheduler-compatible name kept).

    Builds and stores the full SMC daily analysis for every watchlist ticker:
      - Market structure (trend, BOS, CHOCH, swing points)
      - Order blocks (bullish + bearish, unmitigated)
      - Liquidity zones (equal highs / equal lows)
      - Fibonacci retracement levels (current swing)
    """
    from core.indicators import (
        detect_swing_points, detect_market_structure,
        detect_liquidity_zones, detect_order_blocks,
        compute_fibonacci_levels, compute_atr,
    )

    watchlist = ["GOOGL", "MSFT", "TSLA", "AAPL", "SPY"]
    for ticker in watchlist:
        try:
            df = fetch_daily_ohlcv(ticker, lookback_days=60)
            if df is None or df.empty:
                logger.warning("No daily data for %s — cache skipped", ticker)
                continue

            sh_idx, sl_idx = detect_swing_points(df, order=3)
            market_struct  = detect_market_structure(df, sh_idx, sl_idx)
            liquidity_zones = detect_liquidity_zones(df)
            atr_val        = compute_atr(df, period=14)
            order_blocks   = detect_order_blocks(df, sh_idx, sl_idx, atr_val)
            fib            = compute_fibonacci_levels(df, sh_idx, sl_idx, market_struct)

            _analysis_cache[ticker] = {
                "market_structure":  market_struct,
                "order_blocks":      order_blocks,
                "liquidity_zones":   liquidity_zones,
                "fibonacci":         fib,
            }
            logger.info(
                "Analysis cached for %s: trend=%s OBs=%d liq_zones=%d",
                ticker, market_struct.get("trend"),
                len(order_blocks), len(liquidity_zones),
            )
        except Exception as exc:
            logger.error("Cache error for %s: %s", ticker, exc)

        time.sleep(0.2)  # Alpaca rate-limit


def get_cached_analysis(ticker: str) -> Dict:
    """Return the daily analysis cache for *ticker*; empty dict if not cached."""
    return _analysis_cache.get(ticker, {})


# Legacy alias — kept so any stale import in tests still resolves
def get_cached_sr_zones(ticker: str) -> List[Dict]:
    """Deprecated: use get_cached_analysis(). Returns order_blocks list."""
    return _analysis_cache.get(ticker, {}).get("order_blocks", [])
