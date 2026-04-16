"""
learner.py — Weekly self-learning loop.

Runs every Sunday at 8:00 PM ET. Analyses recent trade history, adjusts
strategy parameters, retrains the confidence model, and sends a Discord
learning-update message.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_LEARNING_LOG = os.path.join(_BASE_DIR, "logs", "learning_log.txt")
_WATCHLIST = ["GOOGL", "MSFT", "TSLA", "AAPL", "SPY"]


def _load_config():
    import yaml
    with open(os.path.join(_BASE_DIR, "config.yaml")) as f:
        return yaml.safe_load(f)


def _log_change(message: str) -> None:
    os.makedirs(os.path.dirname(_LEARNING_LOG), exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {message}\n"
    with open(_LEARNING_LOG, "a") as f:
        f.write(line)
    logger.info("Learning: %s", message)


def _compute_stats(trades: List) -> Dict[str, Any]:
    """Return win_rate, avg_win, avg_loss, expectancy for a list of trades."""
    closed = [t for t in trades if t["outcome"] in ("win", "loss") and t["pnl"] is not None]
    if not closed:
        return {"win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "expectancy": 0.0, "n": 0}
    wins = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    win_rate = len(wins) / len(closed)
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    return {
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "n": len(closed),
    }


def _compute_vix_trade_stats(trades: List) -> float:
    """Return win rate on trades taken when VIX was high (>= 25)."""
    high_vix = [t for t in trades
                if t["vix_at_entry"] and t["vix_at_entry"] >= 25.0
                and t["outcome"] in ("win", "loss")]
    if len(high_vix) < 5:
        return 1.0  # not enough data, no adjustment
    wins = sum(1 for t in high_vix if t["outcome"] == "win")
    return wins / len(high_vix)


def run_weekly_learning() -> None:
    """Main entry point: called by APScheduler every Sunday at 8 PM ET."""
    from data import database as db
    from ml import confidence_model
    from notifications import discord_bot

    logger.info("Weekly learning loop started")
    cfg = _load_config()
    min_trades = cfg["ml"]["min_trades_for_learning"]

    trades_30d = db.get_trades_last_n_days(30)
    trades_30d_dicts = [dict(t) for t in trades_30d]
    all_trades = db.get_all_closed_trades()
    all_trades_dicts = [dict(t) for t in all_trades]

    stats = _compute_stats(trades_30d_dicts)
    n_total = db.count_all_trades()

    changes: List[str] = []

    if stats["n"] >= min_trades:
        # ── Rule 1: Overall win rate < 45% → tighten RSI ──
        if stats["win_rate"] < 0.45:
            _adjust_rsi_threshold(db, cfg, tighten=True, changes=changes,
                                  win_rate=stats["win_rate"])

        # ── Rule 2: avg_loss > avg_win * 1.5 → tighten SL ──
        if stats["avg_loss"] > stats["avg_win"] * 1.5 and stats["avg_win"] > 0:
            _adjust_stop_loss(db, changes, win_rate=stats["win_rate"])

        # ── Rule 3: Per-ticker win rate < 40% over 20+ trades ──
        for ticker in _WATCHLIST:
            wr = db.get_win_rate_by_ticker(ticker, min_trades=20)
            if wr is not None and wr < 0.40:
                _reduce_ticker_position_size(db, ticker, changes, win_rate=wr)

        # ── Rule 4: VIX trades consistently losing → raise VIX threshold ──
        vix_wr = _compute_vix_trade_stats(trades_30d_dicts)
        if vix_wr < 0.35:
            _raise_vix_threshold(db, cfg, changes, vix_wr=vix_wr)

        # ── Rule 5: Win rate > 65% for 4+ weeks → loosen RSI by 1 ──
        # Check 4-week win rate as a proxy
        trades_28d = db.get_trades_last_n_days(28)
        stats_28d = _compute_stats([dict(t) for t in trades_28d])
        if stats_28d["win_rate"] > 0.65 and stats_28d["n"] >= 20:
            _adjust_rsi_threshold(db, cfg, tighten=False, changes=changes,
                                  win_rate=stats_28d["win_rate"])
    else:
        logger.info("Not enough trades (%d < %d) for learning adjustments",
                    stats["n"], min_trades)

    # ── Retrain model ──────────────────────────────────────────────────────────
    model_retrained = False
    model_accuracy = None
    if len(all_trades_dicts) >= cfg["ml"]["cold_start_trades"]:
        new_model = confidence_model.train_model(all_trades_dicts)
        model_retrained = new_model is not None
        if model_retrained:
            model_accuracy = confidence_model.get_model_validation_accuracy()

    # ── Discord notification ───────────────────────────────────────────────────
    discord_bot.send_weekly_learning_update(
        n_trades_week=stats["n"],
        win_rate=stats["win_rate"],
        changes=changes,
        model_retrained=model_retrained,
        total_trades=n_total,
        model_accuracy=model_accuracy,
    )

    logger.info("Weekly learning loop complete. %d changes applied.", len(changes))


# ── Adjustment helpers ────────────────────────────────────────────────────────

def _adjust_rsi_threshold(db, cfg: dict, tighten: bool,
                           changes: List[str], win_rate: float) -> None:
    key_oversold = "rsi_oversold"
    key_overbought = "rsi_overbought"
    current_oversold = db.get_strategy_param(key_oversold) or cfg["strategy"]["rsi_oversold"]
    current_overbought = db.get_strategy_param(key_overbought) or cfg["strategy"]["rsi_overbought"]

    if tighten:
        new_oversold = max(20.0, current_oversold - 2.0)
        new_overbought = min(80.0, current_overbought + 2.0)
        reason = f"win_rate={win_rate:.1%} < 45% → tighten RSI by 2pts"
    else:
        new_oversold = min(40.0, current_oversold + 1.0)
        new_overbought = max(60.0, current_overbought - 1.0)
        reason = f"win_rate={win_rate:.1%} > 65% → loosen RSI by 1pt"

    if new_oversold != current_oversold or new_overbought != current_overbought:
        db.upsert_strategy_param(key_oversold, new_oversold, win_rate)
        db.upsert_strategy_param(key_overbought, new_overbought, win_rate)
        msg = f"RSI thresholds adjusted: oversold {current_oversold}→{new_oversold}, " \
              f"overbought {current_overbought}→{new_overbought} ({reason})"
        _log_change(msg)
        changes.append(msg)


def _adjust_stop_loss(db, changes: List[str], win_rate: float) -> None:
    key = "stop_loss_pct"
    current = db.get_strategy_param(key) or 0.25
    new_sl = max(0.15, current - 0.05)  # tighten by 5% (e.g. 25%→20%)
    if new_sl != current:
        db.upsert_strategy_param(key, new_sl, win_rate)
        msg = f"Stop-loss tightened: {current:.0%}→{new_sl:.0%} (avg_loss > 1.5×avg_win)"
        _log_change(msg)
        changes.append(msg)


def _reduce_ticker_position_size(db, ticker: str,
                                  changes: List[str], win_rate: float) -> None:
    key = f"position_size_pct_{ticker}"
    current = db.get_strategy_param(key) or 1.0
    new_size = max(0.25, current * 0.75)  # reduce by 25%
    if abs(new_size - current) > 0.01:
        db.upsert_strategy_param(key, new_size, win_rate)
        msg = f"{ticker} position size reduced: {current:.0%}→{new_size:.0%} " \
              f"(win_rate={win_rate:.1%} < 40% over 20+ trades)"
        _log_change(msg)
        changes.append(msg)


def _raise_vix_threshold(db, cfg: dict, changes: List[str], vix_wr: float) -> None:
    key = "vix_max"
    current = db.get_strategy_param(key) or cfg["strategy"]["vix_max"]
    new_vix = min(40.0, current + 2.0)
    if new_vix != current:
        db.upsert_strategy_param(key, new_vix, vix_wr)
        msg = f"VIX max raised: {current}→{new_vix} " \
              f"(high-VIX trade win_rate={vix_wr:.1%} < 35%)"
        _log_change(msg)
        changes.append(msg)
