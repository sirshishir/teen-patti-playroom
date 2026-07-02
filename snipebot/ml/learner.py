"""
learner.py — Weekly self-learning loop (SMC strategy edition).

Runs every Sunday at 8:00 PM ET.  Analyses the last 30 days of trades,
auto-adjusts SMC strategy parameters, retrains the confidence model,
and sends the Discord Weekly Learning Update.

Adjustment rules (SMC-aware):
  1. Win rate < 45%          → tighten Fibonacci zone (raise fib_zone_min by 0.02)
  2. avg_loss > avg_win×1.5  → tighten stop-loss threshold by 5%
  3. Ticker win rate < 40% over 20+ trades → reduce ticker position size by 25%
  4. VIX trades consistently losing        → raise VIX max threshold by 2
  5. Win rate > 65% for 4+ weeks           → loosen Fibonacci zone (lower fib_zone_min by 0.01)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

_BASE_DIR     = os.path.dirname(os.path.dirname(__file__))
_LEARNING_LOG = os.path.join(_BASE_DIR, "logs", "learning_log.txt")


def _load_config() -> Dict:
    import yaml
    with open(os.path.join(_BASE_DIR, "config.yaml")) as f:
        return yaml.safe_load(f)


def _log_change(message: str) -> None:
    os.makedirs(os.path.dirname(_LEARNING_LOG), exist_ok=True)
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {message}\n"
    with open(_LEARNING_LOG, "a") as f:
        f.write(line)
    logger.info("Learning: %s", message)


def _compute_stats(trades: List[Dict]) -> Dict[str, Any]:
    closed = [t for t in trades
              if t.get("outcome") in ("win", "loss") and t.get("pnl") is not None]
    if not closed:
        return {"win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "expectancy": 0.0, "n": 0}
    wins   = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    wr     = len(wins) / len(closed)
    avg_win  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
    return {
        "win_rate":   round(wr, 4),
        "avg_win":    round(avg_win, 2),
        "avg_loss":   round(avg_loss, 2),
        "expectancy": round(wr * avg_win - (1 - wr) * avg_loss, 2),
        "n":          len(closed),
    }


def _high_vix_win_rate(trades: List[Dict]) -> float:
    high_vix = [t for t in trades
                if (t.get("vix_at_entry") or 0) >= 25.0
                and t.get("outcome") in ("win", "loss")]
    if len(high_vix) < 5:
        return 1.0
    return sum(1 for t in high_vix if t["outcome"] == "win") / len(high_vix)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_weekly_learning() -> None:
    from data import database as db
    from ml import confidence_model
    from notifications import discord_bot

    logger.info("Weekly learning loop started")
    cfg       = _load_config()
    min_trades = cfg["ml"]["min_trades_for_learning"]

    trades_30d      = [dict(t) for t in db.get_trades_last_n_days(30)]
    all_trades      = [dict(t) for t in db.get_all_closed_trades()]
    stats           = _compute_stats(trades_30d)
    n_total         = db.count_all_trades()
    changes: List[str] = []

    if stats["n"] >= min_trades:
        # Rule 1: win rate < 45% → tighten Fibonacci zone
        if stats["win_rate"] < 0.45:
            _tighten_fib_zone(db, cfg, changes, stats["win_rate"])

        # Rule 2: avg_loss > avg_win × 1.5 → tighten stop-loss
        if stats["avg_loss"] > stats["avg_win"] * 1.5 and stats["avg_win"] > 0:
            _adjust_stop_loss(db, cfg, changes, stats["win_rate"])

        # Rule 3: per-ticker win rate < 40% over 20+ trades
        for ticker in db.get_watchlist():
            wr = db.get_win_rate_by_ticker(ticker, min_trades=20)
            if wr is not None and wr < 0.40:
                _reduce_ticker_position_size(db, ticker, changes, wr)

        # Rule 4: high-VIX trades consistently losing
        vix_wr = _high_vix_win_rate(trades_30d)
        if vix_wr < 0.35:
            _raise_vix_threshold(db, cfg, changes, vix_wr)

        # Rule 5: sustained strong win rate → loosen Fibonacci zone slightly
        trades_28d   = [dict(t) for t in db.get_trades_last_n_days(28)]
        stats_28d    = _compute_stats(trades_28d)
        if stats_28d["win_rate"] > 0.65 and stats_28d["n"] >= 20:
            _loosen_fib_zone(db, cfg, changes, stats_28d["win_rate"])
    else:
        logger.info("Not enough trades (%d < %d) for learning adjustments",
                    stats["n"], min_trades)

    # ── Retrain model ──────────────────────────────────────────────────────────
    model_retrained = False
    model_accuracy  = None
    if len(all_trades) >= cfg["ml"]["cold_start_trades"]:
        new_model = confidence_model.train_model(all_trades)
        model_retrained = new_model is not None
        if model_retrained:
            model_accuracy = confidence_model.get_model_validation_accuracy()

    # ── Near-miss analysis ─────────────────────────────────────────────────────
    nm = _near_miss_analysis()

    # ── Discord update ─────────────────────────────────────────────────────────
    discord_bot.send_weekly_learning_update(
        n_trades_week=stats["n"],
        win_rate=stats["win_rate"],
        changes=changes,
        model_retrained=model_retrained,
        total_trades=n_total,
        model_accuracy=model_accuracy,
        near_miss_count=nm["near_miss_count"],
        top_failing_conditions=nm["top_failing"],
        near_miss_win_rate=nm["win_rate"],
    )
    logger.info("Weekly learning complete. %d adjustment(s) applied.", len(changes))


def _near_miss_analysis() -> Dict[str, Any]:
    """Summarise last 7 days of signal candidates for the weekly report."""
    from data import database as db

    candidates  = [dict(c) for c in db.get_signal_candidates_last_n_days(7)]
    fail_stats  = db.get_condition_fail_stats_last_n_days(7)
    threshold   = 9
    near_misses = [c for c in candidates if c["conditions_met"] >= threshold]

    with_outcomes = [c for c in near_misses if c.get("outcome") is not None]
    win_rate = None
    if with_outcomes:
        wins     = sum(1 for c in with_outcomes if c["outcome"] == "would_win")
        win_rate = round(wins / len(with_outcomes) * 100, 1)

    top_failing = sorted(fail_stats.items(), key=lambda x: x[1], reverse=True)[:3]
    top_failing = [(k, n) for k, n in top_failing if n > 0]

    return {
        "near_miss_count": len(near_misses),
        "total_candidates": len(candidates),
        "top_failing":      top_failing,
        "win_rate":         win_rate,
    }


# ── Adjustment helpers ────────────────────────────────────────────────────────

def _tighten_fib_zone(db, cfg: Dict, changes: List[str], win_rate: float) -> None:
    key     = "fib_zone_min"
    current = db.get_strategy_param(key) or cfg["strategy"].get("fib_zone_min", 0.618)
    new_val = min(0.70, current + 0.02)
    if abs(new_val - current) > 0.001:
        db.upsert_strategy_param(key, new_val, win_rate)
        msg = (f"Fibonacci entry zone tightened: fib_zone_min "
               f"{current:.3f}→{new_val:.3f} (win_rate={win_rate:.1%} < 45%)")
        _log_change(msg)
        changes.append(msg)


def _loosen_fib_zone(db, cfg: Dict, changes: List[str], win_rate: float) -> None:
    key     = "fib_zone_min"
    current = db.get_strategy_param(key) or cfg["strategy"].get("fib_zone_min", 0.618)
    new_val = max(0.60, current - 0.01)
    if abs(new_val - current) > 0.001:
        db.upsert_strategy_param(key, new_val, win_rate)
        msg = (f"Fibonacci entry zone loosened: fib_zone_min "
               f"{current:.3f}→{new_val:.3f} (win_rate={win_rate:.1%} > 65%)")
        _log_change(msg)
        changes.append(msg)


def _adjust_stop_loss(db, cfg: Dict, changes: List[str], win_rate: float) -> None:
    key     = "stop_loss_pct"
    current = db.get_strategy_param(key) or cfg["strategy"].get("stop_loss_pct", 0.25)
    new_val = max(0.15, current - 0.05)
    if abs(new_val - current) > 0.001:
        db.upsert_strategy_param(key, new_val, win_rate)
        msg = (f"Stop-loss tightened: {current:.0%}→{new_val:.0%} "
               f"(avg_loss > 1.5 × avg_win)")
        _log_change(msg)
        changes.append(msg)


def _reduce_ticker_position_size(db, ticker: str,
                                  changes: List[str], win_rate: float) -> None:
    key     = f"position_size_pct_{ticker}"
    current = db.get_strategy_param(key) or 1.0
    new_val = max(0.25, current * 0.75)
    if abs(new_val - current) > 0.01:
        db.upsert_strategy_param(key, new_val, win_rate)
        msg = (f"{ticker} position size reduced: {current:.0%}→{new_val:.0%} "
               f"(win_rate={win_rate:.1%} < 40% over 20+ trades)")
        _log_change(msg)
        changes.append(msg)


def _raise_vix_threshold(db, cfg: Dict, changes: List[str], vix_wr: float) -> None:
    key     = "vix_max"
    current = db.get_strategy_param(key) or cfg["strategy"].get("vix_max", 30)
    new_val = min(40.0, current + 2.0)
    if abs(new_val - current) > 0.1:
        db.upsert_strategy_param(key, new_val, vix_wr)
        msg = (f"VIX max raised: {current}→{new_val} "
               f"(high-VIX win_rate={vix_wr:.1%} < 35%)")
        _log_change(msg)
        changes.append(msg)
