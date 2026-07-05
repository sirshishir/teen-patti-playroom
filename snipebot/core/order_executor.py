"""
order_executor.py — Order placement for Alpaca and Webull (paper/live toggle via .env).

Handles:
  - Placing option buy orders
  - Closing option positions (sell-to-close)
  - Recording exits to the database
  - Sending Discord notifications

Broker selection:
  Set the BROKER environment variable to "alpaca" (default) or "webull".
  All other configuration (keys, paper/live mode) is read from the same .env
  as before; Webull additionally requires WEBULL_APP_KEY and WEBULL_APP_SECRET.
"""

import logging
import os
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional

from data import webull_client

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# ── Broker helpers ────────────────────────────────────────────────────────────

def _get_broker() -> str:
    """
    Return the active broker name, lower-cased.
    Reads BROKER env var; defaults to "alpaca".
    Supported values: "alpaca", "webull".
    """
    return os.getenv("BROKER", "alpaca").lower()


def _get_trading_client():
    from alpaca.trading.client import TradingClient
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    paper = os.getenv("TRADING_MODE", "paper").lower() == "paper"
    return TradingClient(api_key, secret_key, paper=paper)


def _get_trading_mode() -> str:
    return os.getenv("TRADING_MODE", "paper").upper()


# ── Place Order ───────────────────────────────────────────────────────────────

def place_option_order(signal: Dict[str, Any]) -> Optional[str]:
    """
    Place a market buy order for the option described in *signal*.
    Routes to Alpaca or Webull depending on the BROKER env var.
    Returns the broker order ID (as a string) if successful, None otherwise.

    signal must contain: option_symbol, qty
    """
    option_symbol = signal.get("option_symbol")
    qty = signal.get("qty", 1)
    ticker = signal.get("ticker", "?")
    direction = signal.get("direction", "?")

    if not option_symbol or not qty:
        logger.error("place_option_order called with missing option_symbol or qty")
        return None

    broker = _get_broker()

    if broker == "webull":
        # ── Webull path ───────────────────────────────────────────────────────
        try:
            result = webull_client.get_webull_client().place_option_order(
                symbol=option_symbol,
                qty=qty,
                side="BUY",
            )
            if result is None:
                logger.error(
                    "Webull place_option_order returned None for %s %s",
                    ticker, option_symbol,
                )
                return None
            order_id = str(result["orderId"])
            logger.info(
                "Webull order placed: %s %s %s qty=%d order_id=%s mode=%s",
                ticker, direction, option_symbol, qty, order_id, _get_trading_mode(),
            )
            return order_id
        except Exception as exc:
            logger.error(
                "Failed to place Webull order for %s %s: %s", ticker, option_symbol, exc
            )
            return None

    else:
        # ── Alpaca path (default) ─────────────────────────────────────────────
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        try:
            client = _get_trading_client()
            req = MarketOrderRequest(
                symbol=option_symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            order = client.submit_order(req)
            order_id = str(order.id)
            logger.info(
                "Alpaca order placed: %s %s %s qty=%d order_id=%s mode=%s",
                ticker, direction, option_symbol, qty, order_id, _get_trading_mode(),
            )
            return order_id
        except Exception as exc:
            logger.error(
                "Failed to place Alpaca order for %s %s: %s", ticker, option_symbol, exc
            )
            return None


# ── Close Position ────────────────────────────────────────────────────────────

def close_position(trade: Any, current_premium: float, exit_reason: str) -> bool:
    """
    Sell-to-close the option held in *trade*.
    Routes to Alpaca or Webull depending on the BROKER env var.
    Updates the database and sends Discord notification.

    Returns True if the close was successful.
    """
    from data import database as db
    from notifications import discord_bot
    from core.risk_manager import cleanup_trail_peak

    def _field(name, default=None):
        # trade may be a sqlite3.Row (no .get) or a dict.
        try:
            val = trade[name]
        except (KeyError, IndexError, TypeError):
            return default
        return val if val is not None else default

    trade_id = trade["id"]
    ticker = trade["ticker"]
    direction = trade["direction"]
    entry_price = trade["entry_price"] or 0.0
    qty = _field("qty", 1) or 1
    option_symbol = _field("option_symbol", "") or ""

    # FIX-10: seed trades are virtual — force the analytical (no-broker) exit
    # path regardless of broker/mode by clearing the option symbol.
    if _field("is_seed", 0):
        option_symbol = ""

    # Calculate PnL
    pnl_per_contract = (current_premium - entry_price) * 100
    pnl = round(pnl_per_contract * qty, 2)
    pnl_pct = round((current_premium - entry_price) / entry_price, 4) if entry_price else 0.0
    outcome = "win" if pnl > 0 else "loss"
    exit_date = date.today().isoformat()

    broker = _get_broker()
    success = False

    if option_symbol:
        if broker == "webull":
            # ── Webull sell path ──────────────────────────────────────────────
            try:
                result = webull_client.get_webull_client().place_option_order(
                    symbol=option_symbol,
                    qty=qty,
                    side="SELL",
                )
                if result is None:
                    logger.error(
                        "Webull close_position returned None for trade_id=%d", trade_id
                    )
                else:
                    success = True
                    logger.info(
                        "Webull closed position trade_id=%d %s %s pnl=%.2f reason=%s",
                        trade_id, ticker, direction, pnl, exit_reason,
                    )
            except Exception as exc:
                logger.error(
                    "Failed to close Webull position trade_id=%d: %s", trade_id, exc
                )

        else:
            # ── Alpaca sell path (default) ────────────────────────────────────
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            try:
                client = _get_trading_client()
                req = MarketOrderRequest(
                    symbol=option_symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
                client.submit_order(req)
                success = True
                logger.info(
                    "Alpaca closed position trade_id=%d %s %s pnl=%.2f reason=%s",
                    trade_id, ticker, direction, pnl, exit_reason,
                )
            except Exception as exc:
                logger.error(
                    "Failed to close Alpaca position trade_id=%d: %s", trade_id, exc
                )
    else:
        # Paper mode without real option symbol — record exit analytically
        logger.info(
            "Analytical exit (no symbol): trade_id=%d pnl=%.2f reason=%s",
            trade_id, pnl, exit_reason,
        )
        success = True

    if success:
        # Update DB
        db.update_trade_exit(
            trade_id=trade_id,
            exit_price=round(current_premium, 2),
            exit_date=exit_date,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            outcome=outcome,
        )
        cleanup_trail_peak(trade_id)

        # Calculate hold time
        entry_date_str = trade.get("entry_date", exit_date)
        try:
            from datetime import date as dt_date
            entry_d = dt_date.fromisoformat(str(entry_date_str))
            exit_d = dt_date.fromisoformat(exit_date)
            hold_days = (exit_d - entry_d).days
            hold_str = f"{hold_days}d"
        except Exception:
            hold_str = "?"

        discord_bot.send_trade_exit(
            ticker=ticker,
            direction=direction,
            entry_price=entry_price,
            exit_price=current_premium,
            pnl=pnl,
            pnl_pct=pnl_pct * 100,
            exit_reason=exit_reason,
            hold_time=hold_str,
        )

        # Check 100-trade milestone
        _check_milestone()

    return success


def _check_milestone() -> None:
    """Send Discord alert at 100-trade milestone."""
    from data import database as db
    from notifications import discord_bot
    n = db.count_all_trades()
    if n == 100:
        closed = db.get_all_closed_trades()
        wins = sum(1 for t in closed if t["outcome"] == "win")
        wr = round(wins / len(closed) * 100, 1) if closed else 0.0
        discord_bot.send_system_alert(
            alert_type="milestone",
            ticker="",
            extra={
                "n_trades": n,
                "win_rate": wr,
            }
        )
