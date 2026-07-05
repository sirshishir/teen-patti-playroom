"""alerts.py — Discord embeds → #day-trade channel (webhook), with dedupe.

Set DISCORD_DAYTRADE_WEBHOOK_URL in .env to a webhook created on the
#day-trade channel (Server Settings → Integrations → Webhooks → New Webhook,
channel = #day-trade). This is intentionally a SEPARATE webhook from
SnipeBot's so each bot owns its channel.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from daytrader import store
from daytrader.data_feed import session_date_str
from daytrader.settings import CONFIG

logger = logging.getLogger(__name__)

_COLOR = {"plan": 0x3498DB, "entry": 0x2ECC71, "invalid": 0xE74C3C,
          "target": 0xF1C40F, "recap": 0x95A5A6, "info": 0x9B59B6}


def _webhook() -> Optional[str]:
    return os.getenv(CONFIG["alerts"]["webhook_env"])


def _post(title: str, description: str, color: int,
          fields: Optional[List[Dict]] = None) -> bool:
    url = _webhook()
    if not url:
        logger.error("%s not set — alert dropped: %s",
                     CONFIG["alerts"]["webhook_env"], title)
        return False
    payload = {"embeds": [{
        "title": title, "description": description[:3900], "color": color,
        "fields": fields or [],
        "footer": {"text": "daytrader • alerts only — not financial advice"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception as exc:
        logger.error("discord post failed: %s", exc)
        return False


def _once(ticker: str, key: str) -> bool:
    """True if this alert_key has NOT fired yet this session (and log it)."""
    sd = session_date_str()
    if store.already_alerted(sd, ticker, key):
        return False
    store.log_alert(sd, ticker, key, datetime.now(timezone.utc).isoformat())
    return True


# ── message types ─────────────────────────────────────────────────────────────

def send_plan(ticker: str, table_str: str, bias: str, version: str = "") -> None:
    key = f"plan{version}"
    if not _once(ticker, key):
        return
    tag = " (confirmed open)" if version else ""
    _post(f"📋 {ticker} Battle Plan{tag} — {session_date_str()}",
          f"**Bias:** {bias}\n```\n{table_str}\n```", _COLOR["plan"])


def send_zone_entry(ticker: str, zone, price: float, confidence: float,
                    sweep_depth: float, entry_no: int) -> None:
    if not _once(ticker, f"entry:{zone.level_type}:{entry_no}"):
        return
    rr = (f"{zone.respect_rate:.0%}" if zone.respect_rate is not None
          else "n/a (calibrating)")
    fields = [
        {"name": "Zone", "value": f"${zone.zone_bottom:,.2f}–${zone.zone_top:,.2f}",
         "inline": True},
        {"name": "Stop", "value": f"${zone.stop:,.2f}", "inline": True},
        {"name": "Targets", "value": f"${zone.target1:,.2f} / ${zone.target2:,.2f}",
         "inline": True},
        {"name": "Confidence", "value": f"{confidence:.0%}", "inline": True},
        {"name": "Level respect rate", "value": rr, "inline": True},
        {"name": "Sweep depth", "value": f"{sweep_depth:.2%}", "inline": True},
    ]
    side = "🟢 LONG" if zone.direction == "long" else "🔴 SHORT"
    _post(f"{side} zone touched — {ticker} @ ${price:,.2f}",
          f"{zone.level_type} ({'+'.join(zone.members)}) — price entered the "
          f"calibrated {'demand' if zone.direction == 'long' else 'supply'} zone.",
          _COLOR["entry"], fields)


def send_invalidation(ticker: str, zone, price: float) -> None:
    if not _once(ticker, f"invalid:{zone.level_type}"):
        return
    _post(f"❌ {ticker} zone invalidated @ ${price:,.2f}",
          f"1-min close beyond stop ${zone.stop:,.2f} "
          f"({zone.level_type}). No trade — stand down on this level.",
          _COLOR["invalid"])


def send_target_hit(ticker: str, zone, which: int, price: float) -> None:
    if not _once(ticker, f"t{which}:{zone.level_type}"):
        return
    tgt = zone.target1 if which == 1 else zone.target2
    _post(f"🎯 {ticker} Target {which} tagged @ ${price:,.2f}",
          f"{zone.level_type} zone → ${tgt:,.2f} reached.", _COLOR["target"])


def send_new_zone(ticker: str, table_str: str, reason: str) -> None:
    if not _once(ticker, f"redraw:{reason}"):
        return
    _post(f"🔄 {ticker} levels redrawn — {reason}",
          f"```\n{table_str}\n```", _COLOR["info"])


def send_recap(ticker: str, events: List[Dict]) -> None:
    if not _once(ticker, "recap"):
        return
    if not events:
        _post(f"🌇 {ticker} recap — {session_date_str()}",
              "No zone touches today.", _COLOR["recap"])
        return
    lines = []
    for e in events:
        out = e.get("outcome") or "pending"
        lines.append(f"• {e['level_type']} {e['direction']} @ "
                     f"${e['touch_price']:,.2f} → **{out}** "
                     f"(conf {e['confidence']:.0%})")
    _post(f"🌇 {ticker} recap — {session_date_str()}",
          "\n".join(lines)[:3900], _COLOR["recap"])


def send_system(msg: str) -> None:
    _post("⚙️ daytrader", msg, _COLOR["info"])


def send_analyst_report(markdown: str) -> None:
    if not _once("ALL", f"analyst:{session_date_str()}"):
        return
    chunks = [markdown[i:i + 3800] for i in range(0, len(markdown), 3800)] \
        or ["(empty)"]
    for i, ch in enumerate(chunks, 1):
        suffix = f" ({i}/{len(chunks)})" if len(chunks) > 1 else ""
        _post(f"📊 Weekly Analyst Review{suffix}", ch, _COLOR["info"])
