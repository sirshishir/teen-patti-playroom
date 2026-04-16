"""
risk_manager.py — Position sizing, daily loss limit enforcement,
and open-position monitoring (take-profit / stop-loss / trail).
"""

import logging
import os
from datetime import date, datetime
from typing import Optional, Dict, Any, List

import yaml

from data import database as db

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def _load_config() -> Dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _get_param(name: str, config_fallback: float) -> float:
    """Read param from DB (learning overrides), falling back to config."""
    val = db.get_strategy_param(name)
    return val if val is not None else config_fallback


# ── Daily Loss Gate ───────────────────────────────────────────────────────────

def daily_loss_limit_hit() -> bool:
    """Return True if today's realised PnL has breached the max daily loss."""
    cfg = _load_config()
    max_loss = cfg["trading"]["max_daily_loss"]
    daily_pnl = db.get_daily_pnl_today()
    return daily_pnl <= -abs(max_loss)


def get_open_position_count() -> int:
    return len(db.get_open_trades())


def max_positions_reached() -> bool:
    cfg = _load_config()
    return get_open_position_count() >= cfg["trading"]["max_open_positions"]


# ── Position Sizing ───────────────────────────────────────────────────────────

def calculate_position_size(ticker: str, premium_per_contract: float) -> Dict[str, Any]:
    """
    Calculate how many contracts to buy, capped at max_position_size.
    Each standard equity option contract = 100 shares.
    Returns dict: {qty, total_cost, max_loss_if_sl, allowed}.
    """
    cfg = _load_config()
    max_pos = cfg["trading"]["max_position_size"]

    # Allow learning engine to reduce size for underperforming tickers
    ticker_size_pct_key = f"position_size_pct_{ticker}"
    size_pct = _get_param(ticker_size_pct_key, 1.0)  # default = 100%
    effective_max = max_pos * size_pct

    if premium_per_contract <= 0:
        return {"qty": 0, "total_cost": 0.0, "max_loss_if_sl": 0.0, "allowed": False}

    cost_per_contract = premium_per_contract * 100  # 1 contract = 100 shares
    qty = max(1, int(effective_max // cost_per_contract))
    total_cost = round(qty * cost_per_contract, 2)

    sl_pct = _get_param("stop_loss_pct", cfg["strategy"]["stop_loss_pct"])
    max_loss_if_sl = round(total_cost * sl_pct, 2)

    allowed = total_cost <= effective_max and qty > 0
    return {
        "qty": qty,
        "total_cost": total_cost,
        "max_loss_if_sl": max_loss_if_sl,
        "allowed": allowed,
    }


# ── Signal Evaluation Gate ────────────────────────────────────────────────────

def evaluate_and_queue(signal: Dict[str, Any]) -> bool:
    """
    Final risk gate before order is placed.
    Returns True if the signal passes all risk checks.
    """
    ticker = signal["ticker"]

    if daily_loss_limit_hit():
        logger.warning("Daily loss limit hit — rejecting signal for %s", ticker)
        return False

    if max_positions_reached():
        logger.info("Max open positions reached — rejecting signal for %s", ticker)
        return False

    if db.traded_ticker_today(ticker):
        logger.info("Already traded %s today — rejecting duplicate signal", ticker)
        return False

    sizing = calculate_position_size(ticker, signal.get("premium", 0.0))
    if not sizing["allowed"]:
        logger.warning("Position size check failed for %s (premium=%.2f)",
                       ticker, signal.get("premium", 0.0))
        return False

    signal["qty"] = sizing["qty"]
    signal["total_cost"] = sizing["total_cost"]
    logger.info("Signal approved for %s: qty=%d total_cost=%.2f",
                ticker, sizing["qty"], sizing["total_cost"])
    return True


# ── Open Position Monitor ─────────────────────────────────────────────────────

def check_open_positions() -> None:
    """
    Called every 1 minute. Checks each open position against TP/SL/trail/time
    conditions and triggers exits if any threshold is breached.
    """
    from core.order_executor import close_position

    cfg = _load_config()
    tp_pct = _get_param("take_profit_pct", cfg["strategy"]["take_profit_pct"])
    sl_pct = _get_param("stop_loss_pct", cfg["strategy"]["stop_loss_pct"])
    trail_trigger = _get_param("trail_trigger_pct", cfg["strategy"]["trail_trigger_pct"])
    trail_stop = _get_param("trail_stop_pct", cfg["strategy"]["trail_stop_pct"])

    open_trades = db.get_open_trades()
    for trade in open_trades:
        trade_id = trade["id"]
        ticker = trade["ticker"]
        entry_price = trade["entry_price"]
        option_symbol = trade.get("exit_reason")  # repurposed field pre-exit — not ideal
        # We store the option symbol in a dedicated column via scanner; retrieve here
        # The option symbol is stored via the trade dict during insertion
        try:
            current_premium = _fetch_current_premium(trade)
        except Exception as exc:
            logger.error("Failed to fetch premium for trade %d: %s", trade_id, exc)
            continue

        if current_premium is None or entry_price is None or entry_price == 0:
            continue

        pnl_pct = (current_premium - entry_price) / entry_price

        exit_reason = _determine_exit(
            trade_id, pnl_pct, tp_pct, sl_pct,
            trail_trigger, trail_stop, trade, entry_price
        )

        if exit_reason:
            close_position(trade, current_premium, exit_reason)


def _fetch_current_premium(trade: Any) -> Optional[float]:
    """Fetch live mid-price of the option held in *trade*."""
    from data.market_data import _fetch_alpaca_options
    ticker = trade["ticker"]
    try:
        chain = _fetch_alpaca_options(ticker, min_dte=0, max_dte=60)
        option_symbol = trade.get("option_symbol", "")
        if option_symbol and not chain.empty:
            row = chain[chain["symbol"] == option_symbol]
            if not row.empty:
                return float(row.iloc[0]["mid"])
    except Exception:
        pass

    # Fallback: use yfinance option chain mid
    import yfinance as yf
    from datetime import date as dt_date
    try:
        t = yf.Ticker(ticker)
        exp_str = trade.get("exit_date", "")  # stored expiry
        if not exp_str:
            return None
        chain = t.option_chain(exp_str)
        direction = trade["direction"]
        df = chain.calls if direction == "call" else chain.puts
        strike = trade.get("entry_price")  # approximate by strike stored separately
        row = df[abs(df["strike"] - strike) < 1.0] if strike else pd.DataFrame()
        if not row.empty:
            return float((row.iloc[0]["bid"] + row.iloc[0]["ask"]) / 2)
    except Exception:
        pass
    return None


# Track trailing stop high-water marks in memory
_trail_peaks: Dict[int, float] = {}


def _determine_exit(trade_id: int, pnl_pct: float,
                    tp_pct: float, sl_pct: float,
                    trail_trigger: float, trail_stop: float,
                    trade: Any, entry_price: float) -> Optional[str]:
    """Return exit reason string or None if position should stay open."""
    # Check time stop: expiry within 1 day
    from datetime import date
    expiry_str = trade.get("expiry", "")
    if expiry_str:
        try:
            expiry = date.fromisoformat(str(expiry_str))
            days_to_expiry = (expiry - date.today()).days
            if days_to_expiry <= 1:
                return "time"
        except ValueError:
            pass

    # Take-profit
    if pnl_pct >= tp_pct:
        return "tp"

    # Stop-loss
    if pnl_pct <= -sl_pct:
        return "sl"

    # Trailing stop
    if pnl_pct >= trail_trigger:
        current_value = entry_price * (1 + pnl_pct)
        peak = _trail_peaks.get(trade_id, current_value)
        if current_value > peak:
            _trail_peaks[trade_id] = current_value
            peak = current_value
        drawdown_from_peak = (peak - current_value) / peak
        if drawdown_from_peak >= trail_stop:
            _trail_peaks.pop(trade_id, None)
            return "trail"

    return None


def cleanup_trail_peak(trade_id: int) -> None:
    _trail_peaks.pop(trade_id, None)
