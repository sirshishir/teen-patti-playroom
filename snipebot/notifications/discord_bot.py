"""
discord_bot.py — All Discord message templates and sender.

Delivery is handled by two layers (auto-detected, in priority order):
  1. Gateway bot   — the persistent discord.py client in discord_client.py
                     (set DISCORD_BOT_TOKEN; posts to #price-alert). This also
                     powers the interactive "Show Analysis" command.
  2. Webhook       — set DISCORD_WEBHOOK_URL (fallback if the gateway bot is
                     not running).

All six message types are defined here:
  1. Trade Entry
  2. Trade Exit
  3. Daily Report
  4. Weekly Learning Update
  5. Daily Loss Limit Hit
  6. System Alerts (data errors, online status, milestone)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from notifications import discord_client

logger = logging.getLogger(__name__)

_WEBHOOK_URL_ENV = "DISCORD_WEBHOOK_URL"
_TIMEOUT = 10  # seconds


def _get_webhook_url() -> Optional[str]:
    url = os.getenv(_WEBHOOK_URL_ENV, "")
    return url if url else None


def _send(payload: Dict[str, Any]) -> bool:
    """
    Deliver *payload* to Discord. Prefers the live gateway bot (discord.py);
    falls back to a webhook if the gateway isn't connected. Returns True on
    success.
    """
    content = payload.get("content", "")

    # 1. Live gateway bot (discord.py) — also posts strictly to #price-alert
    if discord_client.is_running():
        if discord_client.post(content):
            return True
        logger.warning("Gateway post failed — trying webhook fallback")

    # 2. Webhook fallback
    url = _get_webhook_url()
    if not url:
        logger.warning(
            "No Discord delivery available — gateway bot not connected and "
            "DISCORD_WEBHOOK_URL not set — message not sent"
        )
        return False
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        if resp.status_code in (200, 204):
            return True
        logger.error("Discord webhook returned %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("Discord send error: %s", exc)
        return False


def _now_et_str() -> str:
    import pytz
    et = pytz.timezone("US/Eastern")
    return datetime.now(et).strftime("%Y-%m-%d %H:%M:%S ET")


# ── Message 1 — Trade Entry ───────────────────────────────────────────────────

def send_trade_entry(
    ticker: str,
    direction: str,
    strike: float,
    expiry: str,
    dte: int,
    premium: float,
    qty: int,
    total_cost: float,
    rsi: float,
    macd_signal: str,
    vol_ratio: float,
    confidence: float,
    zone_low: float,
    zone_high: float,
    zone_touches: int,
) -> bool:
    tp_price = round(premium * 1.40, 2)
    sl_price = round(premium * 0.75, 2)
    content = (
        f"🎯 SNIPE FIRED — {ticker} {direction.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Direction: {direction.upper()}\n"
        f"💰 Strike: ${strike} | Expiry: {expiry} ({dte} DTE)\n"
        f"🏷️ Premium: ${premium}/contract | {qty} contracts = ${total_cost}\n"
        f"📊 RSI: {rsi:.1f} | MACD: {macd_signal} | Vol: {vol_ratio:.2f}x avg\n"
        f"🧠 AI Confidence: {confidence:.1f}%\n"
        f"🛡️ S/R Zone: ${zone_low}–${zone_high} ({zone_touches} touches)\n"
        f"🎯 TP: +40% → ${tp_price} | SL: -25% → ${sl_price}\n"
        f"⏰ Time: {_now_et_str()}"
    )
    return _send({"content": content})


# ── Message 2 — Trade Exit ────────────────────────────────────────────────────

def send_trade_exit(
    ticker: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    pnl: float,
    pnl_pct: float,
    exit_reason: str,
    hold_time: str,
) -> bool:
    icon = "✅ WIN" if pnl >= 0 else "❌ LOSS"
    reason_map = {"tp": "Take Profit", "sl": "Stop Loss",
                  "time": "Time Stop", "trail": "Trailing Stop"}
    reason_str = reason_map.get(exit_reason, exit_reason)
    sign = "+" if pnl >= 0 else ""
    content = (
        f"{icon} POSITION CLOSED — {ticker} {direction.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 Exit Reason: {reason_str}\n"
        f"💵 Entry: ${entry_price} → Exit: ${exit_price}\n"
        f"📈 P&L: {sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)\n"
        f"⏱️ Hold Time: {hold_time}"
    )
    return _send({"content": content})


# ── Message 3 — Daily Report ──────────────────────────────────────────────────

def send_daily_report(
    report_date: str,
    total_trades: int,
    wins: int,
    losses: int,
    daily_pnl: float,
    open_count: int,
    portfolio_value: float,
    pct_change: float,
    signals_scanned: int,
    fired: int,
    avg_confidence: float,
    best_trade: float,
    worst_trade: float,
    win_rate_30d: float,
) -> bool:
    sign = "+" if daily_pnl >= 0 else ""
    content = (
        f"📊 SNIPEBOT DAILY REPORT — {report_date}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Trades Today: {total_trades} | ✅ Wins: {wins} | ❌ Losses: {losses}\n"
        f"💰 Daily P&L: {sign}${daily_pnl:.2f}\n"
        f"📦 Open Positions: {open_count}\n"
        f"💼 Portfolio Value: ${portfolio_value:.2f} ({pct_change:+.1f}% from start)\n"
        f"🔍 Signals Scanned: {signals_scanned} | Fired: {fired}\n"
        f"🧠 Avg AI Confidence Today: {avg_confidence:.1f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 Best Trade: ${best_trade:+.2f}\n"
        f"💀 Worst Trade: ${worst_trade:+.2f}\n"
        f"📈 Win Rate (last 30 days): {win_rate_30d:.1f}%"
    )
    return _send({"content": content})


# ── Message 3b — Near-Miss Signal ────────────────────────────────────────────

_NEAR_MISS_LABELS = {
    "weekly_bias":     "Weekly bias",
    "daily_structure": "Daily structure",
    "liquidity_sweep": "Liquidity sweep",
    "fibonacci_zone":  "Fibonacci zone",
    "order_block":     "Order block",
    "rvol":            "RVOL",
    "atr_expansion":   "ATR expansion",
    "session_score":   "Session timing",
    "ai_confidence":   "AI confidence",
    "earnings_clear":  "Earnings clear",
    "vix_ok":          "VIX ok",
    "not_eod":         "Not end-of-day",
}


def send_near_miss_signal(
    ticker: str,
    direction: str,
    conditions_met: int,
    cond_results: Dict[str, bool],
    indicators: Dict[str, Any],
    confidence: float,
    vix: float,
) -> bool:
    detail: Dict[str, str] = {
        "rvol":          f"{indicators.get('rvol', 0):.1f}×",
        "atr_expansion": f"ratio {indicators.get('atr_expansion_ratio', 0):.2f}",
        "ai_confidence": f"{confidence * 100:.0f}%",
        "vix_ok":        f"VIX {vix:.1f}",
    }
    lines = []
    for key, label in _NEAR_MISS_LABELS.items():
        icon   = "✅" if cond_results.get(key) else "❌"
        suffix = f" ({detail[key]})" if key in detail and not cond_results.get(key) else ""
        lines.append(f"{icon} {label}{suffix}")

    content = (
        f"\U0001f4ca NEAR-MISS — {ticker} {direction.upper()} ({conditions_met}/12)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{chr(10).join(lines)}\n"
        f"⏰ {_now_et_str()}"
    )
    return _send({"content": content})


# ── Message 4 — Weekly Learning Update ───────────────────────────────────────

def send_weekly_learning_update(
    n_trades_week: int,
    win_rate: float,
    changes: List[str],
    model_retrained: bool,
    total_trades: int,
    model_accuracy: Optional[float],
    near_miss_count: int = 0,
    top_failing_conditions: Optional[List] = None,
    near_miss_win_rate: Optional[float] = None,
) -> bool:
    changes_str = (
        "\n".join(f"  • {c}" for c in changes)
        if changes else "  No changes needed"
    )
    accuracy_str = f"{model_accuracy:.1f}%" if model_accuracy is not None else "N/A"

    # Near-miss section
    if top_failing_conditions:
        label_map = {
            "cond_weekly_bias": "Weekly bias", "cond_daily_structure": "Daily structure",
            "cond_liquidity_sweep": "Liquidity sweep", "cond_fibonacci_zone": "Fibonacci zone",
            "cond_order_block": "Order block", "cond_rvol": "RVOL",
            "cond_atr_expansion": "ATR expansion", "cond_session_score": "Session timing",
            "cond_ai_confidence": "AI confidence", "cond_earnings_clear": "Earnings clear",
            "cond_vix_ok": "VIX", "cond_not_eod": "End-of-day",
        }
        blockers = " | ".join(
            f"{label_map.get(k, k)} ({n}×)"
            for k, n in top_failing_conditions[:3]
        )
    else:
        blockers = "N/A"

    wr_str = f"{near_miss_win_rate:.1f}%" if near_miss_win_rate is not None else "N/A"

    content = (
        f"🧠 WEEKLY LEARNING UPDATE\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Trades This Week: {n_trades_week} | Win Rate: {win_rate:.1%}\n"
        f"🔧 Parameters Adjusted:\n{changes_str}\n"
        f"🤖 Model Retrained: {'Yes' if model_retrained else 'No'} "
        f"({total_trades} total trades in memory)\n"
        f"📈 Model Accuracy: {accuracy_str} on validation set\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Near-Misses This Week (≥9/12): {near_miss_count}\n"
        f"❌ Top Blockers: {blockers}\n"
        f"📊 Near-Miss Directional Accuracy: {wr_str}"
    )
    return _send({"content": content})


# ── Message 5 — Daily Loss Limit Hit ─────────────────────────────────────────

def send_daily_loss_limit(amount: float, ticker: str,
                           direction: str, pnl: float) -> bool:
    content = (
        f"⚠️ DAILY LOSS LIMIT HIT\n"
        f"Bot has lost ${amount:.2f} today. Trading HALTED until tomorrow.\n"
        f"Last trade: {ticker} {direction.upper()} ${pnl:+.2f}"
    )
    return _send({"content": content})


# ── Message 6 — System Alerts ─────────────────────────────────────────────────

def send_system_alert(alert_type: str, ticker: str,
                       extra: Dict[str, Any]) -> bool:
    """
    alert_type: 'data_error' | 'online' | 'milestone'
    """
    if alert_type == "data_error":
        content = (
            f"🔴 MARKET DATA ERROR — {ticker}\n"
            f"Failed to fetch data 3 times in a row. "
            f"Scanning paused for 15 minutes."
        )
    elif alert_type == "online":
        mode = extra.get("mode", "PAPER")
        watchlist = "GOOGL, MSFT, TSLA, AAPL, SPY"
        ts = _now_et_str()
        content = (
            f"🟢 SnipeBot is ONLINE — {ts}\n"
            f"Mode: {mode} | Watching: {watchlist}"
        )
    elif alert_type == "milestone":
        n = extra.get("n_trades", 100)
        wr = extra.get("win_rate", 0.0)
        content = (
            f"📊 {n} TRADES MILESTONE REACHED\n"
            f"Paper trading complete with {n} trades. Win rate: {wr:.1f}%.\n"
            f"Review logs/learning_log.txt before switching to live trading.\n"
            f"Manual .env change required to go live. Bot will NOT auto-switch."
        )
    else:
        content = f"⚠️ SYSTEM ALERT [{alert_type}]: {extra}"

    return _send({"content": content})


# ── Online Announcement ───────────────────────────────────────────────────────

def announce_online() -> bool:
    mode = os.getenv("TRADING_MODE", "paper").upper()
    return send_system_alert("online", "", {"mode": mode})
