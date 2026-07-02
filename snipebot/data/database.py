"""
database.py — SQLite interface for SnipeBot.
Handles all CRUD operations for trades, strategy_params, and daily_performance.
"""

import sqlite3
import logging
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

_DATA_DIR = os.getenv("SNIPEBOT_DATA_DIR", os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(_DATA_DIR, "snipebot.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables if they don't exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS trades (
        id              INTEGER PRIMARY KEY,
        ticker          TEXT,
        direction       TEXT,
        entry_price     REAL,
        exit_price      REAL,
        entry_date      TEXT,
        exit_date       TEXT,
        pnl             REAL,
        pnl_pct         REAL,
        exit_reason     TEXT,
        rsi_at_entry    REAL,
        macd_signal     TEXT,
        volume_ratio    REAL,
        sr_zone_quality REAL,
        vix_at_entry    REAL,
        ai_confidence   REAL,
        market_regime   TEXT,
        outcome         TEXT
    );

    CREATE TABLE IF NOT EXISTS strategy_params (
        id                  INTEGER PRIMARY KEY,
        param_name          TEXT UNIQUE,
        param_value         REAL,
        last_updated        TEXT,
        win_rate_when_set   REAL
    );

    CREATE TABLE IF NOT EXISTS daily_performance (
        date          TEXT PRIMARY KEY,
        total_trades  INTEGER,
        wins          INTEGER,
        losses        INTEGER,
        gross_pnl     REAL,
        best_trade    REAL,
        worst_trade   REAL,
        notes         TEXT
    );

    CREATE TABLE IF NOT EXISTS signal_candidates (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker               TEXT    NOT NULL,
        direction            TEXT    NOT NULL,
        scan_time            TEXT    NOT NULL,
        entry_price          REAL,
        conditions_met       INTEGER DEFAULT 0,
        cond_weekly_bias     INTEGER DEFAULT 0,
        cond_daily_structure INTEGER DEFAULT 0,
        cond_liquidity_sweep INTEGER DEFAULT 0,
        cond_fibonacci_zone  INTEGER DEFAULT 0,
        cond_order_block     INTEGER DEFAULT 0,
        cond_rvol            INTEGER DEFAULT 0,
        cond_atr_expansion   INTEGER DEFAULT 0,
        cond_session_score   INTEGER DEFAULT 0,
        cond_ai_confidence   INTEGER DEFAULT 0,
        cond_earnings_clear  INTEGER DEFAULT 0,
        cond_vix_ok          INTEGER DEFAULT 0,
        cond_not_eod         INTEGER DEFAULT 0,
        ai_confidence_score  REAL,
        fired                INTEGER DEFAULT 0,
        underlying_move_pct  REAL,
        outcome              TEXT
    );

    CREATE TABLE IF NOT EXISTS watchlist (
        ticker    TEXT PRIMARY KEY,
        added_at  TEXT
    );
    """
    with get_connection() as conn:
        conn.executescript(ddl)
    _seed_watchlist()
    logger.info("Database initialised at %s", DB_PATH)


# ── Watchlist ─────────────────────────────────────────────────────────────────

_DEFAULT_WATCHLIST = ["GOOGL", "MSFT", "TSLA", "AAPL", "SPY"]


def _seed_watchlist() -> None:
    """Populate the watchlist with defaults on first run (if empty)."""
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        if n == 0:
            now = datetime.utcnow().isoformat()
            conn.executemany(
                "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?)",
                [(t, now) for t in _DEFAULT_WATCHLIST],
            )
            logger.info("Seeded watchlist with defaults: %s", _DEFAULT_WATCHLIST)


def get_watchlist() -> List[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist ORDER BY added_at ASC"
        ).fetchall()
    return [r["ticker"] for r in rows] or list(_DEFAULT_WATCHLIST)


def add_to_watchlist(ticker: str) -> bool:
    """Add *ticker* (upper-cased). Returns False if it was already present."""
    ticker = ticker.strip().upper()
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM watchlist WHERE ticker=?", (ticker,)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?)", (ticker, now)
        )
    return True


def remove_from_watchlist(ticker: str) -> bool:
    ticker = ticker.strip().upper()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))
    return cur.rowcount > 0


# ── Near-miss alert thresholds (stored in strategy_params) ─────────────────────

def set_global_near_miss_threshold(value: int) -> None:
    upsert_strategy_param("near_miss_threshold", float(value))


def set_ticker_near_miss_threshold(ticker: str, value: int) -> None:
    upsert_strategy_param(f"near_miss_threshold_{ticker.strip().upper()}", float(value))


def get_near_miss_threshold(ticker: str, default: int) -> int:
    """Effective threshold for *ticker*: per-ticker override → global → default."""
    per = get_strategy_param(f"near_miss_threshold_{ticker.strip().upper()}")
    if per is not None:
        return int(per)
    glob = get_strategy_param("near_miss_threshold")
    if glob is not None:
        return int(glob)
    return int(default)


# ── Trades ────────────────────────────────────────────────────────────────────

def insert_trade(trade: Dict[str, Any]) -> int:
    sql = """
    INSERT INTO trades (
        ticker, direction, entry_price, exit_price, entry_date, exit_date,
        pnl, pnl_pct, exit_reason, rsi_at_entry, macd_signal, volume_ratio,
        sr_zone_quality, vix_at_entry, ai_confidence, market_regime, outcome
    ) VALUES (
        :ticker, :direction, :entry_price, :exit_price, :entry_date, :exit_date,
        :pnl, :pnl_pct, :exit_reason, :rsi_at_entry, :macd_signal, :volume_ratio,
        :sr_zone_quality, :vix_at_entry, :ai_confidence, :market_regime, :outcome
    )
    """
    with get_connection() as conn:
        cur = conn.execute(sql, trade)
        trade_id = cur.lastrowid
    logger.debug("Inserted trade id=%d ticker=%s", trade_id, trade.get("ticker"))
    return trade_id


def update_trade_exit(trade_id: int, exit_price: float, exit_date: str,
                      pnl: float, pnl_pct: float, exit_reason: str,
                      outcome: str) -> None:
    sql = """
    UPDATE trades
    SET exit_price=?, exit_date=?, pnl=?, pnl_pct=?, exit_reason=?, outcome=?
    WHERE id=?
    """
    with get_connection() as conn:
        conn.execute(sql, (round(exit_price, 2), exit_date,
                           round(pnl, 2), round(pnl_pct, 4),
                           exit_reason, outcome, trade_id))
    logger.debug("Updated trade id=%d exit_reason=%s pnl=%.2f", trade_id, exit_reason, pnl)


def get_open_trades() -> List[sqlite3.Row]:
    sql = "SELECT * FROM trades WHERE exit_date IS NULL OR exit_date = ''"
    with get_connection() as conn:
        return conn.execute(sql).fetchall()


def get_trades_last_n_days(days: int) -> List[sqlite3.Row]:
    sql = """
    SELECT * FROM trades
    WHERE entry_date >= date('now', ?)
    ORDER BY entry_date DESC
    """
    with get_connection() as conn:
        return conn.execute(sql, (f"-{days} days",)).fetchall()


def get_all_closed_trades() -> List[sqlite3.Row]:
    sql = """
    SELECT * FROM trades
    WHERE exit_date IS NOT NULL AND exit_date != ''
    ORDER BY entry_date ASC
    """
    with get_connection() as conn:
        return conn.execute(sql).fetchall()


def count_all_trades() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM trades").fetchone()
        return row[0]


def traded_ticker_today(ticker: str) -> bool:
    today = date.today().isoformat()
    sql = "SELECT 1 FROM trades WHERE ticker=? AND entry_date=? LIMIT 1"
    with get_connection() as conn:
        return conn.execute(sql, (ticker, today)).fetchone() is not None


def get_today_closed_trades() -> List[sqlite3.Row]:
    today = date.today().isoformat()
    sql = "SELECT * FROM trades WHERE entry_date=? AND exit_date IS NOT NULL"
    with get_connection() as conn:
        return conn.execute(sql, (today,)).fetchall()


def get_daily_pnl_today() -> float:
    today = date.today().isoformat()
    sql = "SELECT COALESCE(SUM(pnl), 0.0) FROM trades WHERE entry_date=? AND pnl IS NOT NULL"
    with get_connection() as conn:
        row = conn.execute(sql, (today,)).fetchone()
        return round(row[0], 2)


# ── Strategy Params ───────────────────────────────────────────────────────────

def upsert_strategy_param(name: str, value: float, win_rate: float = 0.0) -> None:
    now = datetime.utcnow().isoformat()
    sql = """
    INSERT INTO strategy_params (param_name, param_value, last_updated, win_rate_when_set)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(param_name) DO UPDATE SET
        param_value=excluded.param_value,
        last_updated=excluded.last_updated,
        win_rate_when_set=excluded.win_rate_when_set
    """
    with get_connection() as conn:
        conn.execute(sql, (name, value, now, win_rate))


def get_strategy_param(name: str) -> Optional[float]:
    sql = "SELECT param_value FROM strategy_params WHERE param_name=?"
    with get_connection() as conn:
        row = conn.execute(sql, (name,)).fetchone()
        return row["param_value"] if row else None


def get_all_strategy_params() -> Dict[str, float]:
    with get_connection() as conn:
        rows = conn.execute("SELECT param_name, param_value FROM strategy_params").fetchall()
        return {r["param_name"]: r["param_value"] for r in rows}


# ── Daily Performance ─────────────────────────────────────────────────────────

def upsert_daily_performance(perf: Dict[str, Any]) -> None:
    sql = """
    INSERT INTO daily_performance
        (date, total_trades, wins, losses, gross_pnl, best_trade, worst_trade, notes)
    VALUES
        (:date, :total_trades, :wins, :losses, :gross_pnl, :best_trade, :worst_trade, :notes)
    ON CONFLICT(date) DO UPDATE SET
        total_trades=excluded.total_trades,
        wins=excluded.wins,
        losses=excluded.losses,
        gross_pnl=excluded.gross_pnl,
        best_trade=excluded.best_trade,
        worst_trade=excluded.worst_trade,
        notes=excluded.notes
    """
    with get_connection() as conn:
        conn.execute(sql, perf)


def get_daily_performance(for_date: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM daily_performance WHERE date=?", (for_date,)
        ).fetchone()


def get_win_rate_last_n_days(days: int) -> float:
    trades = get_trades_last_n_days(days)
    closed = [t for t in trades if t["outcome"] in ("win", "loss")]
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t["outcome"] == "win")
    return round(wins / len(closed), 4)


# ── Signal Candidates ─────────────────────────────────────────────────────────

_COND_COLS = [
    "cond_weekly_bias", "cond_daily_structure", "cond_liquidity_sweep",
    "cond_fibonacci_zone", "cond_order_block", "cond_rvol", "cond_atr_expansion",
    "cond_session_score", "cond_ai_confidence", "cond_earnings_clear",
    "cond_vix_ok", "cond_not_eod",
]


def insert_signal_candidate(row: Dict[str, Any]) -> int:
    sql = """
    INSERT INTO signal_candidates (
        ticker, direction, scan_time, entry_price, conditions_met,
        cond_weekly_bias, cond_daily_structure, cond_liquidity_sweep,
        cond_fibonacci_zone, cond_order_block, cond_rvol, cond_atr_expansion,
        cond_session_score, cond_ai_confidence, cond_earnings_clear,
        cond_vix_ok, cond_not_eod, ai_confidence_score, fired
    ) VALUES (
        :ticker, :direction, :scan_time, :entry_price, :conditions_met,
        :cond_weekly_bias, :cond_daily_structure, :cond_liquidity_sweep,
        :cond_fibonacci_zone, :cond_order_block, :cond_rvol, :cond_atr_expansion,
        :cond_session_score, :cond_ai_confidence, :cond_earnings_clear,
        :cond_vix_ok, :cond_not_eod, :ai_confidence_score, :fired
    )
    """
    with get_connection() as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid


def update_candidate_fired(candidate_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE signal_candidates SET fired=1 WHERE id=?", (candidate_id,))


def update_candidate_outcome(candidate_id: int,
                              underlying_move_pct: float, outcome: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE signal_candidates SET underlying_move_pct=?, outcome=? WHERE id=?",
            (round(underlying_move_pct, 2), outcome, candidate_id),
        )


def get_todays_candidates() -> List[sqlite3.Row]:
    today = date.today().isoformat()
    sql = "SELECT * FROM signal_candidates WHERE scan_time LIKE ? ORDER BY scan_time ASC"
    with get_connection() as conn:
        return conn.execute(sql, (f"{today}%",)).fetchall()


def get_signal_candidates_last_n_days(days: int) -> List[sqlite3.Row]:
    sql = """
    SELECT * FROM signal_candidates
    WHERE scan_time >= date('now', ?)
    ORDER BY scan_time DESC
    """
    with get_connection() as conn:
        return conn.execute(sql, (f"-{days} days",)).fetchall()


def get_condition_fail_stats_last_n_days(days: int) -> Dict[str, int]:
    """Return how many times each condition failed in the last *days* days."""
    rows = get_signal_candidates_last_n_days(days)
    counts: Dict[str, int] = {col: 0 for col in _COND_COLS}
    for row in rows:
        for col in _COND_COLS:
            if not row[col]:
                counts[col] += 1
    return counts


def get_win_rate_by_ticker(ticker: str, min_trades: int = 1) -> Optional[float]:
    sql = """
    SELECT outcome FROM trades
    WHERE ticker=? AND outcome IN ('win','loss')
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (ticker,)).fetchall()
    if len(rows) < min_trades:
        return None
    wins = sum(1 for r in rows if r["outcome"] == "win")
    return round(wins / len(rows), 4)
