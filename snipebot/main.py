"""
main.py — SnipeBot entry point.

Initialises logging, database, and APScheduler with all jobs.
Sends the Discord "online" message on startup.
Handles market holiday detection before each intraday session.
"""

import logging
import logging.handlers
import os
import sys

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# ── Bootstrap ─────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add snipebot root to sys.path so relative imports work when run directly
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Load .env before importing any module that reads env vars
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ── Logging Setup ─────────────────────────────────────────────────────────────

def setup_logging() -> None:
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "snipebot.log")
    handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="D", interval=1, backupCount=7, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(console)


setup_logging()
logger = logging.getLogger(__name__)

# ── Deferred imports (after logging + dotenv) ─────────────────────────────────

from data import database as db
from data.market_data import is_market_open_today, cache_sr_zones
from core.scanner import run_scan
from core.risk_manager import check_open_positions, daily_loss_limit_hit
from reports.daily_report import send_report
from ml.learner import run_weekly_learning
from notifications.discord_bot import announce_online

ET = pytz.timezone("US/Eastern")

# ── Market-guard wrappers ─────────────────────────────────────────────────────

def _guarded_scan() -> None:
    """Run scanner only if market is open and loss limit not hit."""
    if not is_market_open_today():
        return
    if daily_loss_limit_hit():
        logger.info("Daily loss limit active — scan skipped")
        return
    run_scan()


def _guarded_position_check() -> None:
    if not is_market_open_today():
        return
    check_open_positions()


def _guarded_sr_cache() -> None:
    if not is_market_open_today():
        return
    cache_sr_zones()


def _guarded_daily_report() -> None:
    if not is_market_open_today():
        return
    send_report()


# ── Scheduler Setup ───────────────────────────────────────────────────────────

def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=ET)

    # S/R zone cache — daily 9:00 AM ET, Mon–Fri
    scheduler.add_job(
        _guarded_sr_cache,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=ET),
        id="sr_cache",
        name="Cache S/R Zones",
        misfire_grace_time=300,
    )

    # Market scanner — every 5 min, Mon–Fri, 9:35–15:45 ET
    scheduler.add_job(
        _guarded_scan,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/5",
            timezone=ET,
        ),
        id="scanner",
        name="Market Scanner",
        misfire_grace_time=60,
    )

    # Open position monitor — every 1 min, Mon–Fri, 9:35–15:55 ET
    scheduler.add_job(
        _guarded_position_check,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*",
            timezone=ET,
        ),
        id="position_monitor",
        name="Position Monitor",
        misfire_grace_time=30,
    )

    # Daily report — 4:15 PM ET, Mon–Fri
    scheduler.add_job(
        _guarded_daily_report,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=15, timezone=ET),
        id="daily_report",
        name="Daily Report",
        misfire_grace_time=600,
    )

    # Weekly learning — Sunday 8:00 PM ET
    scheduler.add_job(
        run_weekly_learning,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=ET),
        id="weekly_learning",
        name="Weekly Learning",
        misfire_grace_time=3600,
    )

    return scheduler


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("SnipeBot starting up...")

    # Ensure models/ and logs/ directories exist
    os.makedirs(os.path.join(BASE_DIR, "models"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

    # Initialise database (create tables if not exist)
    db.init_db()

    # Announce online via Discord
    try:
        announce_online()
    except Exception as exc:
        logger.warning("Failed to send online announcement: %s", exc)

    # Build and start scheduler
    scheduler = build_scheduler()
    logger.info("APScheduler starting with %d jobs", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logger.info("  Job: %s | %s", job.id, job.name)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("SnipeBot shutting down")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
