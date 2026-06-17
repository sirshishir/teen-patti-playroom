"""
webull_client.py — Webull Developer API REST client (OAuth2 client_credentials).

Authentication flow:
  POST /oauth2/token with app_key + app_secret → Bearer token stored in memory.
  Token is refreshed automatically when it expires or a 401 is received.

IMPORTANT: All endpoint paths below are best-guess based on the Webull Developer
API documentation structure. Verify every path against your actual account docs
at developer.webull.com before going live. Paths are annotated with
"# verify path" comments.

Environment variables read by get_webull_client():
  WEBULL_APP_KEY    — App Key from developer.webull.com
  WEBULL_APP_SECRET — App Secret from developer.webull.com
  TRADING_MODE      — "paper" (default) or "live"
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base URLs — verify against developer.webull.com if these change
# ---------------------------------------------------------------------------
PAPER_BASE_URL = "https://paper-api.webull.com"
LIVE_BASE_URL  = "https://api.webull.com"

# Request timeout in seconds for all calls
_TIMEOUT = 15

# Module-level singleton so repeated calls reuse the same token
_client_instance: Optional["WebullClient"] = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class WebullClient:
    """
    Thin wrapper around the Webull Developer REST API.

    Parameters
    ----------
    app_key    : App Key from developer.webull.com
    app_secret : App Secret from developer.webull.com
    paper      : True → paper-trading base URL; False → live base URL
    """

    def __init__(self, app_key: str, app_secret: str, paper: bool = True) -> None:
        self._app_key    = app_key
        self._app_secret = app_secret
        self._base_url   = PAPER_BASE_URL if paper else LIVE_BASE_URL
        self._token: Optional[str] = None
        self._token_expiry: float  = 0.0   # unix epoch seconds
        logger.info("WebullClient initialised (paper=%s, base=%s)", paper, self._base_url)

    # ── Authentication ────────────────────────────────────────────────────────

    def _authenticate(self) -> None:
        """
        Obtain a Bearer token via OAuth2 client_credentials grant.

        Endpoint: POST /oauth2/token          # verify path
        Body: {"app_key": ..., "app_secret": ..., "grant_type": "client_credentials"}
        Response expected fields: access_token, expires_in (seconds)
        """
        url = f"{self._base_url}/oauth2/token"  # verify path
        payload: Dict[str, str] = {
            "app_key":    self._app_key,
            "app_secret": self._app_secret,
            "grant_type": "client_credentials",
        }
        logger.debug("Authenticating with Webull at %s", url)
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as exc:
            logger.error("Webull authentication request failed: %s", exc)
            raise

        token = data.get("access_token")
        if not token:
            raise ValueError(
                f"Webull auth response did not contain access_token. "
                f"Response keys: {list(data.keys())}"
            )

        expires_in = int(data.get("expires_in", 3600))
        # Subtract 60 s as a safety margin so we refresh before true expiry
        self._token        = token
        self._token_expiry = time.time() + expires_in - 60
        logger.info("Webull token obtained; valid for ~%d seconds", expires_in - 60)

    def _is_token_valid(self) -> bool:
        return self._token is not None and time.time() < self._token_expiry

    def _get_headers(self) -> Dict[str, str]:
        """
        Return HTTP headers with a valid Bearer token.
        Calls _authenticate() if the token is absent or expired.
        """
        if not self._is_token_valid():
            logger.debug("Token absent or expired — re-authenticating")
            self._authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
        }

    # ── Generic request wrapper ───────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        retry_on_401: bool = True,
        **kwargs: Any,
    ) -> Any:
        """
        Execute an HTTP request against the Webull API.

        Automatically:
          - Injects current Authorization header
          - Re-authenticates once on 401 then retries
          - Raises on non-2xx responses
          - Returns parsed JSON

        Parameters
        ----------
        method : HTTP verb ("GET", "POST", "DELETE", etc.)
        path   : URL path (e.g. "/api/trade/v1/orders")
        kwargs : Passed directly to requests.request (json=, params=, etc.)
        """
        url     = f"{self._base_url}{path}"
        headers = self._get_headers()
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                timeout=_TIMEOUT,
                **kwargs,
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Webull request %s %s failed: %s", method, url, exc)
            return None

        if resp.status_code == 401 and retry_on_401:
            logger.warning("Received 401 on %s — refreshing token and retrying", path)
            self._token = None  # force re-auth
            return self._request(method, path, retry_on_401=False, **kwargs)

        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logger.error(
                "Webull HTTP error %s on %s %s: %s",
                resp.status_code, method, url, exc,
            )
            return None

        try:
            return resp.json()
        except ValueError as exc:
            logger.error("Webull non-JSON response from %s: %s", url, exc)
            return None

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account(self) -> Optional[Dict]:
        """
        Retrieve account summary (balances, buying power, etc.).

        Endpoint: GET /api/account/v1/account      # verify path
        Returns dict or None on failure.
        """
        result = self._request("GET", "/api/account/v1/account")  # verify path
        if result is None:
            logger.error("get_account returned None")
        return result

    # ── Positions ─────────────────────────────────────────────────────────────

    def get_positions(self) -> Optional[List[Dict]]:
        """
        Retrieve open positions.

        Endpoint: GET /api/trade/v1/positions      # verify path
        Returns list of position dicts or None on failure.
        """
        result = self._request("GET", "/api/trade/v1/positions")  # verify path
        if result is None:
            logger.error("get_positions returned None")
            return None
        # API may wrap list in a key; handle both list and {"data": [...]}
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("positions", []))
        return result

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_option_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MKT",
    ) -> Optional[Dict]:
        """
        Place an option order (buy or sell).

        Endpoint: POST /api/trade/v1/orders        # verify path

        Parameters
        ----------
        symbol     : OCC option symbol (e.g. "AAPL240119C00150000")
        qty        : Number of contracts
        side       : "BUY" or "SELL"
        order_type : "MKT" (market) or "LMT" (limit); default "MKT"

        Returns dict with at least {"orderId": "..."} or None on failure.
        """
        payload: Dict[str, Any] = {
            "symbol":      symbol,
            "qty":         qty,
            "side":        side.upper(),
            "orderType":   order_type,
            "timeInForce": "DAY",
        }
        logger.info(
            "Placing Webull option order: %s %s qty=%d type=%s",
            side, symbol, qty, order_type,
        )
        result = self._request("POST", "/api/trade/v1/orders", json=payload)  # verify path
        if result is None:
            logger.error("place_option_order: no response for %s %s", side, symbol)
        return result

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """
        Cancel an open order by ID.

        Endpoint: DELETE /api/trade/v1/orders/{order_id}    # verify path

        Returns API response dict or None on failure.
        """
        path = f"/api/trade/v1/orders/{order_id}"  # verify path
        logger.info("Cancelling Webull order_id=%s", order_id)
        result = self._request("DELETE", path)
        if result is None:
            logger.error("cancel_order: no response for order_id=%s", order_id)
        return result

    # ── Market Data — Bars ────────────────────────────────────────────────────

    def get_bars(
        self,
        symbol: str,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV bars for a symbol.

        Endpoint: GET /api/market/v1/bars          # verify path

        Parameters
        ----------
        symbol   : Ticker symbol (e.g. "AAPL")
        interval : One of "1Hour", "4Hour", "1Day", "1Week" (mapped internally)
        start_dt : Start datetime (timezone-aware or naive UTC)
        end_dt   : End datetime (timezone-aware or naive UTC)

        Interval mapping to Webull API codes (verify against your docs):
          "1Hour"  → "60"
          "4Hour"  → "240"
          "1Day"   → "1D"
          "1Week"  → "1W"

        Returns DataFrame with lowercase columns: open, high, low, close, volume
        Index is a DatetimeIndex in UTC. Returns None on failure or empty response.
        """
        interval_map: Dict[str, str] = {
            "1Hour": "60",    # verify mapping
            "4Hour": "240",   # verify mapping
            "1Day":  "1D",    # verify mapping
            "1Week": "1W",    # verify mapping
        }
        api_interval = interval_map.get(interval, interval)

        def _to_ts(dt: datetime) -> str:
            """Convert datetime to ISO-8601 string expected by the API."""
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        params: Dict[str, str] = {
            "symbol":    symbol,
            "interval":  api_interval,
            "startTime": _to_ts(start_dt),  # verify param name
            "endTime":   _to_ts(end_dt),    # verify param name
        }
        logger.debug(
            "get_bars: symbol=%s interval=%s (%s) start=%s end=%s",
            symbol, interval, api_interval, params["startTime"], params["endTime"],
        )
        result = self._request("GET", "/api/market/v1/bars", params=params)  # verify path
        if not result:
            logger.error("get_bars: empty or None response for %s", symbol)
            return None

        # API may return {"data": [...]} or a bare list — handle both
        bars: List[Dict] = []
        if isinstance(result, list):
            bars = result
        elif isinstance(result, dict):
            bars = result.get("data", result.get("bars", []))

        if not bars:
            logger.warning("get_bars: no bar data in response for %s", symbol)
            return None

        try:
            df = pd.DataFrame(bars)
            # Normalise column names to lowercase
            df.columns = [c.lower() for c in df.columns]
            # Expect a time/timestamp column — common names from Webull docs
            time_col = next(
                (c for c in df.columns if c in ("time", "timestamp", "t", "datetime")),
                None,
            )
            if time_col:
                df.index = pd.to_datetime(df[time_col], utc=True)
                df = df.drop(columns=[time_col])
            # Keep only OHLCV columns if present; rename common short variants
            rename_map = {
                "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
            }
            df = df.rename(columns=rename_map)
            ohlcv_cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            df = df[ohlcv_cols].apply(pd.to_numeric, errors="coerce")
            if df.empty:
                logger.warning(
                    "get_bars: DataFrame is empty after normalisation for %s", symbol
                )
                return None
            return df
        except Exception as exc:
            logger.error("get_bars: failed to parse bars for %s: %s", symbol, exc)
            return None

    # ── Market Data — Options Chain ───────────────────────────────────────────

    def get_option_chain(
        self,
        symbol: str,
        exp_date_from: str,
        exp_date_to: str,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch the options chain for a symbol filtered by expiry range.

        Endpoint: GET /api/market/v1/options/chain     # verify path

        Parameters
        ----------
        symbol        : Underlying ticker (e.g. "AAPL")
        exp_date_from : ISO-8601 date string "YYYY-MM-DD" (inclusive)
        exp_date_to   : ISO-8601 date string "YYYY-MM-DD" (inclusive)

        Returns DataFrame with columns:
            symbol, strike, expiry, option_type, bid, ask, mid, dte
        Returns None on failure or empty chain.
        """
        params: Dict[str, str] = {
            "symbol":      symbol,
            "expDateFrom": exp_date_from,  # verify param name
            "expDateTo":   exp_date_to,    # verify param name
        }
        logger.debug(
            "get_option_chain: %s expiry %s → %s", symbol, exp_date_from, exp_date_to
        )
        result = self._request(
            "GET", "/api/market/v1/options/chain", params=params  # verify path
        )
        if not result:
            logger.error("get_option_chain: empty or None response for %s", symbol)
            return None

        # Normalise to a flat list of contract dicts
        contracts: List[Dict] = []
        if isinstance(result, list):
            contracts = result
        elif isinstance(result, dict):
            contracts = result.get("data", result.get("options", result.get("chain", [])))

        if not contracts:
            logger.warning("get_option_chain: no contracts in response for %s", symbol)
            return None

        rows = []
        from datetime import date as dt_date
        today = datetime.now(tz=timezone.utc).date()
        for c in contracts:
            # Field names are best-guess from common Webull API patterns.
            # Verify against developer.webull.com documentation.
            expiry_str = (
                c.get("expiry")
                or c.get("expDate")
                or c.get("expiration")
                or c.get("expirationDate", "")
            )
            try:
                expiry_date = dt_date.fromisoformat(str(expiry_str)[:10])
                dte = (expiry_date - today).days
            except (ValueError, TypeError):
                dte = None
                expiry_date = expiry_str

            bid = c.get("bid") or c.get("bidPrice")
            ask = c.get("ask") or c.get("askPrice")
            mid = (
                (float(bid) + float(ask)) / 2
                if bid is not None and ask is not None
                else None
            )
            rows.append({
                "symbol":      c.get("symbol") or c.get("optionSymbol", ""),
                "strike":      c.get("strike") or c.get("strikePrice"),
                "expiry":      str(expiry_date),
                "option_type": (
                    c.get("type") or c.get("optionType") or c.get("side", "")
                ).lower(),
                "bid":         float(bid) if bid is not None else None,
                "ask":         float(ask) if ask is not None else None,
                "mid":         mid,
                "dte":         dte,
            })

        if not rows:
            logger.warning(
                "get_option_chain: could not parse any contracts for %s", symbol
            )
            return None

        df = pd.DataFrame(rows)
        logger.info(
            "get_option_chain: %d contracts for %s (%s → %s)",
            len(df), symbol, exp_date_from, exp_date_to,
        )
        return df


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def get_webull_client() -> WebullClient:
    """
    Return a cached WebullClient instance.

    Reads environment variables:
      WEBULL_APP_KEY    — required
      WEBULL_APP_SECRET — required
      TRADING_MODE      — "paper" (default) or "live"

    The instance is cached at module level so subsequent calls reuse the same
    token without re-authenticating on every request.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    app_key    = os.getenv("WEBULL_APP_KEY", "")
    app_secret = os.getenv("WEBULL_APP_SECRET", "")
    paper      = os.getenv("TRADING_MODE", "paper").lower() == "paper"

    if not app_key or not app_secret:
        logger.warning(
            "WEBULL_APP_KEY or WEBULL_APP_SECRET not set; "
            "Webull API calls will fail authentication"
        )

    _client_instance = WebullClient(app_key=app_key, app_secret=app_secret, paper=paper)
    return _client_instance
