"""
analysis_snapshot.py — Build the on-demand "current analysis" report.

Triggered by the Discord "Show Analysis" command. Produces a compact,
Discord-friendly (< 2000 char) summary of the live SMC state for every
watchlist ticker, plus a full 12-condition ✅/❌ breakdown for the ticker
closest to firing.
"""

import logging
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)

_ET = pytz.timezone("US/Eastern")

_COND_LABELS = {
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


def _dir_icon(direction) -> str:
    return {"call": "🟢 CALL", "put": "🔴 PUT"}.get(direction, "⚪ —")


def build_analysis_report() -> str:
    """Return the formatted analysis string (blocking; does network I/O)."""
    from core.scanner import analyze_watchlist

    rows = analyze_watchlist()
    now  = datetime.now(_ET).strftime("%Y-%m-%d %H:%M:%S ET")

    lines = [f"📈 CURRENT ANALYSIS — {now}", "━━━━━━━━━━━━━━━━━━━━"]

    available = [r for r in rows if r.get("available")]
    if not available:
        lines.append("No analysis available yet — waiting for the 9 AM ET "
                     "daily cache to populate. Try again after market open.")
        return "\n".join(lines)

    # Per-ticker one-liners
    for r in rows:
        if not r.get("available"):
            lines.append(f"• {r['ticker']}: data unavailable")
            continue
        price = r.get("price") or 0.0
        lines.append(
            f"• {r['ticker']} ${price:.2f} | {_dir_icon(r.get('direction'))} | "
            f"W:{r.get('weekly_trend')} D:{r.get('structure')} | "
            f"{r['conditions_met']}/12 | conf {r['confidence'] * 100:.0f}%"
        )

    # Full breakdown for the ticker closest to firing
    best = max(available, key=lambda r: r["conditions_met"])
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔍 Closest setup — {best['ticker']} "
                 f"({best['conditions_met']}/12):")
    conds = best.get("conditions", {})
    for key, label in _COND_LABELS.items():
        icon = "✅" if conds.get(key) else "❌"
        lines.append(f"{icon} {label}")

    text = "\n".join(lines)
    if len(text) > 2000:
        text = text[:1997] + "..."
    return text
