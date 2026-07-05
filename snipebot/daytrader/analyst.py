"""analyst.py — weekly Claude-powered research analyst (meta-learner).

Division of labor:
  * The bot LEARNS WITHOUT Claude: nightly quantiles/respect rates and the
    weekly RandomForest retrain are pure statistics.
  * Claude is the layer ABOVE that learning: it audits the week's labeled
    touches (label quality, timeout rates, alerted-vs-suppressed performance,
    holdout-accuracy drift), narrates regime shifts, and — only with strong
    evidence — proposes a CONFIG-ONLY change.

Proposals never touch main and never deploy anything. They land on a branch
`daytrader/proposal-<ISOWEEK>` with a PR for human review. Deployment stays
weekly + manual: merge → `git pull` → restart the service.

Schedule: Sundays 19:30 ET (after the 19:00 retrain), or run manually:
    python -m daytrader.analyst
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import requests
import yaml

from daytrader import alerts, store
from daytrader.settings import CONFIG

logger = logging.getLogger(__name__)

_A = CONFIG.get("analyst") or {}
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)                    # snipebot dir (inside the git repo)
_CONFIG_PATH = os.path.join(_HERE, "config.yaml")
_ALLOWED_TOP = {"levels", "calibration", "scorer", "data", "tickers"}
_API_URL = "https://api.anthropic.com/v1/messages"

_SYSTEM = """You are the weekly research analyst for an intraday levels alert bot.
You receive one JSON blob: the week's labeled zone-touch outcomes per ticker+level_type,
alerted-vs-suppressed performance, current calibration quantiles, last model retrain
metrics, and the current config.

Respond with ONLY a JSON object (no markdown fences, no prose outside JSON):
{"report_markdown": "<weekly review: what worked, what degraded, label-quality issues,
regime observations, and any code/feature IDEAS as prose>",
 "regime_flags": ["<short flag>", ...],
 "proposals": []}

proposals may contain AT MOST ONE item:
{"summary": "<8 words>", "config_updates": {"<dot.path>": <value>},
 "rationale": "...", "evidence": "..."}
config_updates keys MUST start with one of: "levels.", "calibration.", "scorer.",
"data." — or be exactly "tickers". Nothing else (never alerts/storage/webhooks).
Propose ONLY if the affected level_type has >=30 labeled touches in the window AND the
effect persisted across >=5 sessions. Otherwise return "proposals": [].
Code or feature changes are NEVER proposals — describe them in report_markdown only."""


def _week_bounds() -> Tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=7)).isoformat(), today.isoformat()


def gather_context() -> Dict:
    start, end = _week_bounds()
    events = [e for e in store.labeled_events()
              if start <= (e.get("session_date") or "") <= end]
    thr = float(CONFIG["scorer"]["min_confidence_alert"])
    per: Dict[str, Dict] = {}
    for e in events:
        d = per.setdefault(f"{e['ticker']}:{e['level_type']}", {
            "n": 0, "win": 0, "loss": 0, "timeout": 0,
            "alerted_n": 0, "alerted_win": 0,
            "suppressed_n": 0, "suppressed_win": 0,
            "avg_mfe": 0.0, "avg_mae": 0.0,
        })
        d["n"] += 1
        d[e["outcome"]] = d.get(e["outcome"], 0) + 1
        d["avg_mfe"] += float(e.get("mfe") or 0)
        d["avg_mae"] += float(e.get("mae") or 0)
        bucket = "alerted" if float(e.get("confidence") or 0) >= thr else "suppressed"
        d[f"{bucket}_n"] += 1
        if e["outcome"] == "win":
            d[f"{bucket}_win"] += 1
    for d in per.values():
        d["avg_mfe"] = round(d["avg_mfe"] / d["n"], 3)
        d["avg_mae"] = round(d["avg_mae"] / d["n"], 3)

    retrain = None
    rp = os.path.join(_BASE, os.path.dirname(CONFIG["scorer"]["model_path"]),
                      "last_retrain.json")
    if os.path.exists(rp):
        try:
            with open(rp) as f:
                retrain = json.load(f)
        except Exception:
            pass

    return {
        "week": {"start": start, "end": end},
        "labeled_events_week": len(events),
        "total_labeled": store.count_labeled(),
        "per_level": per,
        "calibration": {t: store.get_calibration(t) for t in CONFIG["tickers"]},
        "last_retrain": retrain,
        "current_config": {k: CONFIG[k] for k in _ALLOWED_TOP if k in CONFIG},
    }


def ask_claude(context: Dict) -> Optional[Dict]:
    key = os.getenv(_A.get("api_key_env", "ANTHROPIC_API_KEY"))
    if not key:
        logger.warning("analyst: %s not set — skipping weekly analysis",
                       _A.get("api_key_env", "ANTHROPIC_API_KEY"))
        return None
    try:
        r = requests.post(_API_URL, timeout=120, headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": _A.get("model", "claude-sonnet-4-6"),
            "max_tokens": 3000,
            "system": _SYSTEM,
            "messages": [{"role": "user",
                          "content": json.dumps(context, default=str)}],
        })
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", [])
                       if b.get("type") == "text").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        return json.loads(text)
    except Exception as exc:
        logger.error("analyst: Claude call failed: %s", exc)
        return None


def _apply_updates(updates: Dict) -> Optional[str]:
    """Return new config.yaml text with dot-path updates, or None if any key
    is outside the whitelist."""
    if not updates:
        return None
    with open(_CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    for path, val in updates.items():
        parts = str(path).split(".")
        if parts[0] not in _ALLOWED_TOP:
            logger.warning("analyst: rejected config key %s", path)
            return None
        node = cfg
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return yaml.safe_dump(cfg, sort_keys=False)


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=_BASE,
                          capture_output=True, text=True)


def open_proposal(new_yaml: str, prop: Dict, report: str) -> Optional[str]:
    week = datetime.now(timezone.utc).strftime("%G-W%V")
    branch = f"daytrader/proposal-{week}"
    if _git("rev-parse", "--verify", branch).returncode == 0:
        logger.info("analyst: %s exists — one proposal per week", branch)
        return None
    cur = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
    rel = os.path.relpath(_CONFIG_PATH, _BASE)
    try:
        if _git("checkout", "-b", branch).returncode != 0:
            raise RuntimeError("branch create failed")
        with open(_CONFIG_PATH, "w") as f:
            f.write(new_yaml)
        _git("add", rel)
        c = _git("commit", "-m",
                 f"daytrader weekly proposal {week}: {prop.get('summary', '')}")
        if c.returncode != 0:
            raise RuntimeError(f"commit failed: {c.stderr[:200]}")
        p = _git("push", "-u", "origin", branch)
        if p.returncode != 0:
            raise RuntimeError(f"push failed: {p.stderr[:200]}")
        body = (
            f"## Weekly analyst proposal ({week})\n\n"
            f"**Summary:** {prop.get('summary')}\n\n"
            f"**Config updates:** `{json.dumps(prop.get('config_updates'))}`\n\n"
            f"**Rationale:** {prop.get('rationale')}\n\n"
            f"**Evidence:** {prop.get('evidence')}\n\n"
            "**Before merging:** run the walk-forward backtest on this branch vs "
            "main (see `.claude/skills/day-trader`).\n"
            "**After merging (weekly deploy):** `git pull && systemctl restart "
            "daytrader` (or `fly deploy`).\n\n---\n\n" + report[:2000]
        )
        pr = subprocess.run(
            ["gh", "pr", "create", "--head", branch,
             "--title", f"daytrader proposal {week}: {prop.get('summary', '')}",
             "--body", body],
            cwd=_BASE, capture_output=True, text=True)
        if pr.returncode == 0 and pr.stdout.strip():
            return pr.stdout.strip()
        logger.warning("analyst: gh pr create failed: %s", pr.stderr[:200])
        return branch                      # branch pushed; PR can be opened by hand
    except Exception as exc:
        logger.error("analyst: proposal failed: %s", exc)
        return None
    finally:
        _git("checkout", "--", rel)        # drop any uncommitted config edit
        _git("checkout", cur)


def run_weekly() -> None:
    ctx = gather_context()
    out = ask_claude(ctx)
    if not out:
        return
    report = out.get("report_markdown") or "(empty report)"
    flags = out.get("regime_flags") or []
    if flags:
        report += "\n\n**Regime flags:** " + " | ".join(str(f) for f in flags)
    alerts.send_analyst_report(report)

    props = out.get("proposals") or []
    if not props:
        return
    gate = int(_A.get("min_labeled_events_week", 15))
    if ctx["labeled_events_week"] < gate:
        alerts.send_system(
            f"🧪 Analyst suggested a change but the evidence gate blocked it "
            f"({ctx['labeled_events_week']} labeled events this week < {gate}). "
            "Report only.")
        return
    prop = props[0]
    new_yaml = _apply_updates(dict(prop.get("config_updates") or {}))
    if not new_yaml:
        alerts.send_system("🧪 Analyst proposal rejected (disallowed/empty config keys).")
        return
    if not _A.get("enable_pr", True):
        alerts.send_system("📝 Weekly proposal (PR mode off):\n```json\n"
                           + json.dumps(prop, indent=2)[:1500] + "\n```")
        return
    ref = open_proposal(new_yaml, prop, report)
    if ref:
        alerts.send_system(
            f"🔀 Weekly proposal ready: {ref}\nReview the diff and merge when "
            "satisfied — deploy stays weekly (pull + restart after merge).")
    else:
        alerts.send_system(
            "⚠️ Proposal branch/PR failed (see logs). Suggested diff:\n```json\n"
            + json.dumps(prop.get("config_updates"), indent=2) + "\n```")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    store.init_db()
    run_weekly()
