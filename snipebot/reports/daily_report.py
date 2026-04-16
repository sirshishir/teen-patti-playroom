"""
daily_report.py — End-of-day report generator.

Called daily at 4:15 PM ET. Collects today's trade stats, portfolio value,
persists to daily_performance table, and sends the Discord daily report.
"""

import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_STARTING_CAPITAL = 2000.0  # read from config if needed


def _load_config():
    import yaml
    with open(os.path.join(_BASE_DIR, "config.yaml")) as f:
        return yaml.safe_load(f)


def send_report() -> None:
    """Assemble and send the daily performance report."""
    from data import database as db
    from notifications import discord_bot
    from core.scanner import get_session_stats, reset_session_stats

    cfg = _load_config()
    today = date.today().isoformat()

    # ── Trade stats for today ──
    today_trades = db.get_today_closed_trades()
    open_trades = db.get_open_trades()

    total = len(today_trades)
    wins = sum(1 for t in today_trades if t["outcome"] == "win")
    losses = sum(1 for t in today_trades if t["outcome"] == "loss")
    daily_pnl = sum(t["pnl"] for t in today_trades if t["pnl"] is not None)
    daily_pnl = round(daily_pnl, 2)

    pnls = [t["pnl"] for t in today_trades if t["pnl"] is not None]
    best_trade = round(max(pnls), 2) if pnls else 0.0
    worst_trade = round(min(pnls), 2) if pnls else 0.0

    open_count = len(open_trades)

    # ── Portfolio value (starting capital + all realised PnL) ──
    all_closed = db.get_all_closed_trades()
    total_realised = sum(t["pnl"] for t in all_closed if t["pnl"] is not None)
    starting = cfg["trading"]["capital"]
    portfolio_value = round(starting + total_realised, 2)
    pct_change = round((portfolio_value - starting) / starting * 100, 2)

    # ── Scanner session stats ──
    stats = get_session_stats()

    # ── 30-day win rate ──
    win_rate_30d = db.get_win_rate_last_n_days(30) * 100

    # ── Persist to DB ──
    db.upsert_daily_performance({
        "date": today,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "gross_pnl": daily_pnl,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "notes": "",
    })

    # ── Check daily loss limit and notify if hit ──
    if daily_pnl <= -abs(cfg["trading"]["max_daily_loss"]):
        last_ticker = today_trades[-1]["ticker"] if today_trades else "?"
        last_dir = today_trades[-1]["direction"] if today_trades else "?"
        last_pnl = today_trades[-1]["pnl"] if today_trades else 0.0
        discord_bot.send_daily_loss_limit(
            amount=abs(daily_pnl),
            ticker=last_ticker,
            direction=last_dir,
            pnl=last_pnl,
        )

    # ── Send Discord report ──
    discord_bot.send_daily_report(
        report_date=today,
        total_trades=total,
        wins=wins,
        losses=losses,
        daily_pnl=daily_pnl,
        open_count=open_count,
        portfolio_value=portfolio_value,
        pct_change=pct_change,
        signals_scanned=stats["signals_scanned"],
        fired=stats["fired"],
        avg_confidence=stats["avg_confidence"],
        best_trade=best_trade,
        worst_trade=worst_trade,
        win_rate_30d=win_rate_30d,
    )

    logger.info("Daily report sent: trades=%d pnl=%.2f portfolio=%.2f",
                total, daily_pnl, portfolio_value)

    # Reset session counters for next trading day
    reset_session_stats()
