"""store.py — SQLite persistence for the day-trade alerts bot.

Tables
------
zone_events    : every zone touch (the ML training set — labeled nightly)
sweep_samples  : per-session wick-overshoot measurements (calibration input)
calibration    : rolling q50/q90 overshoot + respect rate per ticker+level_type
alert_log      : dedupe guard so an alert key fires once per session
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_path() -> str:
    from daytrader.settings import CONFIG
    p = CONFIG["storage"]["db_path"]
    return p if os.path.isabs(p) else os.path.join(_BASE_DIR, p)


@contextmanager
def _conn():
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS zone_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT, session_date TEXT, level_type TEXT, direction TEXT,
            level REAL, zone_top REAL, zone_bottom REAL, stop REAL,
            target1 REAL, target2 REAL,
            touch_time TEXT, touch_price REAL,
            sweep_depth REAL, rvol REAL, session_minute INTEGER,
            vwap_dist_atr REAL, confluence INTEGER, confidence REAL,
            outcome TEXT, outcome_minutes REAL, mfe REAL, mae REAL
        );
        CREATE TABLE IF NOT EXISTS sweep_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT, session_date TEXT, level_type TEXT, overshoot REAL
        );
        CREATE TABLE IF NOT EXISTS calibration (
            ticker TEXT, level_type TEXT,
            q50 REAL, q90 REAL, respect_rate REAL,
            n_samples INTEGER, n_labeled INTEGER, updated TEXT,
            PRIMARY KEY (ticker, level_type)
        );
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT, ticker TEXT, alert_key TEXT, sent_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_events_pending
            ON zone_events (session_date) WHERE outcome IS NULL;
        """)


# ── zone events ───────────────────────────────────────────────────────────────

def insert_zone_event(row: Dict[str, Any]) -> int:
    cols = ("ticker session_date level_type direction level zone_top zone_bottom "
            "stop target1 target2 touch_time touch_price sweep_depth rvol "
            "session_minute vwap_dist_atr confluence confidence").split()
    with _conn() as c:
        cur = c.execute(
            f"INSERT INTO zone_events ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})",
            [row.get(k) for k in cols],
        )
        return int(cur.lastrowid)


def pending_events(session_date: str) -> List[Dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM zone_events WHERE outcome IS NULL AND session_date=?",
            (session_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def label_event(event_id: int, outcome: str, minutes: float,
                mfe: float, mae: float) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE zone_events SET outcome=?, outcome_minutes=?, mfe=?, mae=? "
            "WHERE id=?",
            (outcome, minutes, mfe, mae, event_id),
        )


def labeled_events(limit: Optional[int] = None) -> List[Dict]:
    q = ("SELECT * FROM zone_events WHERE outcome IN ('win','loss') "
         "ORDER BY touch_time")
    if limit:
        q += f" LIMIT {int(limit)}"
    with _conn() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def count_labeled() -> int:
    with _conn() as c:
        (n,) = c.execute(
            "SELECT COUNT(*) FROM zone_events WHERE outcome IN ('win','loss')"
        ).fetchone()
    return int(n)


def events_for_session(session_date: str) -> List[Dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM zone_events WHERE session_date=?", (session_date,)
        ).fetchall()]


# ── calibration ───────────────────────────────────────────────────────────────

def insert_sweep_samples(rows: List[Dict]) -> None:
    with _conn() as c:
        c.executemany(
            "INSERT INTO sweep_samples (ticker, session_date, level_type, overshoot) "
            "VALUES (:ticker, :session_date, :level_type, :overshoot)", rows,
        )


def sweep_samples(ticker: str, level_type: str, window_sessions: int) -> List[float]:
    with _conn() as c:
        rows = c.execute(
            "SELECT overshoot FROM sweep_samples WHERE ticker=? AND level_type=? "
            "AND session_date >= (SELECT MIN(d) FROM (SELECT DISTINCT session_date d "
            "FROM sweep_samples WHERE ticker=? ORDER BY d DESC LIMIT ?)) ",
            (ticker, level_type, ticker, window_sessions),
        ).fetchall()
    return [float(r[0]) for r in rows]


def upsert_calibration(ticker: str, level_type: str, q50: float, q90: float,
                       respect_rate: float, n_samples: int, n_labeled: int,
                       updated: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO calibration VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, level_type) DO UPDATE SET q50=excluded.q50, "
            "q90=excluded.q90, respect_rate=excluded.respect_rate, "
            "n_samples=excluded.n_samples, n_labeled=excluded.n_labeled, "
            "updated=excluded.updated",
            (ticker, level_type, q50, q90, respect_rate, n_samples, n_labeled, updated),
        )


def get_calibration(ticker: str) -> Dict[str, Dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM calibration WHERE ticker=?", (ticker,)
        ).fetchall()
    return {r["level_type"]: dict(r) for r in rows}


# ── alert dedupe ──────────────────────────────────────────────────────────────

def already_alerted(session_date: str, ticker: str, alert_key: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM alert_log WHERE session_date=? AND ticker=? AND alert_key=?",
            (session_date, ticker, alert_key),
        ).fetchone()
    return row is not None


def log_alert(session_date: str, ticker: str, alert_key: str, sent_at: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO alert_log (session_date, ticker, alert_key, sent_at) "
            "VALUES (?,?,?,?)", (session_date, ticker, alert_key, sent_at),
        )
