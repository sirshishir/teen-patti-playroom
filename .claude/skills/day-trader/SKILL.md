---
name: day-trader
description: Architecture, invariants, and workflows for the daytrader alerts bot inside the snipebot repo. Use this skill whenever the task touches anything under daytrader/, mentions the #day-trade Discord channel, intraday levels, entry/stop/target zones, liquidity sweeps, wick overshoots, calibration quantiles, triple-barrier labeling, the zone scorer, or the walk-forward backtest — even if the user just says "the day trade bot", "levels bot", or "why didn't I get an alert".
---

# day-trader — maintainer's guide

An **alerts-only** intraday levels bot. It never places orders. It posts to the
**#day-trade** Discord channel via `DISCORD_DAYTRADE_WEBHOOK_URL`.

**Sibling skill:** `day-trade-methodology` holds the trading doctrine (why
zones are calibrated, regime filters, validation ritual, playbooks). Consult
it for any change to trading LOGIC; this file covers the CODE. A strategy
change that satisfies this file but violates the methodology skill is wrong.

## Mental model (read before editing anything)

1. **Data** (`data_feed.py`): free-tier hybrid. SIP (100% of tape) for anything
   older than 16 min; real-time IEX for the tail. Rows overlapping prefer SIP.
   Never "simplify" this to one feed — the split IS the product: exact wicks
   for free.
2. **Levels** (`levels_engine.py`): reference levels (PDH/PDL/PDC, PMH/PML,
   OPEN, HOD/LOD, VWAP, round numbers) → **calibrated zones**. A demand zone is
   NOT drawn at the textbook level: `zone_bottom = level·(1−q50)` and
   `stop = level·(1−q90) − 0.1·ATR`, where q50/q90 are that ticker+level-type's
   measured wick-overshoot quantiles. This is the anti-stop-hunt mechanism.
   All functions are pure (frames + calib dict in, zones out) so live and
   backtest share one code path. Preserve that purity.
3. **Learning loop** (`calibrate.py` + `scorer.py`): every zone *touch* is a
   training sample (no fill needed). Nightly (18:30 ET): re-measure overshoots
   on the day's pure-SIP data, triple-barrier-label pending touches
   (win/loss/timeout; both-barriers-in-one-bar = loss), refresh rolling
   quantiles + respect rates. Weekly (Sun): retrain the RandomForest; below 50
   labeled events the heuristic in `scorer.heuristic_score` is used.
4. **Alerts** (`alerts.py` + `main.py`): event-driven, never periodic spam.
   Plan at 09:15 + confirmed 09:40, zone-entry on transition into the zone
   (with hysteresis: re-arm only after price leaves by 0.5·ATR, max 2
   entries/zone/session), invalidation on 1-min close through the stop,
   target tags, 16:05 recap. Dedupe lives in `store.alert_log` keyed per
   session — check `_once()` before adding any new alert type.

5. **Weekly analyst** (`analyst.py`): the Claude API meta-layer. Sundays 19:30
   it reads the week's labeled events + calibration deltas + retrain metrics,
   posts a review to #day-trade, and may open ONE branch
   `daytrader/proposal-<ISOWEEK>` changing ONLY `daytrader/config.yaml`, with a
   PR for the human. It is a proposer, never an operator: the statistical
   learning (quantiles, respect rates, RF weights) runs entirely without it.

## Invariants — do not violate

- **Never** add order placement, broker mutations, or `TradingClient` order
  calls to this package. If the user asks, surface the PDT constraint and ask
  for explicit confirmation as a separate project.
- SIP requests must keep `end ≤ now − 16 min` unless the account has Algo
  Trader Plus (env flag would be a new feature — ask first).
- `adjustment=Adjustment.ALL` on every bars request.
- Backtest (`backtest.py`) must stay walk-forward: day D uses calibration from
  days < D only; today's overshoots fold in AFTER the day is simulated.
- Zone-touch events are inserted for **every** touch, even when the alert is
  confidence-suppressed — that's the training data.
- No new pip dependencies without flagging it.
- The analyst may modify ONLY `daytrader/config.yaml`, ONLY on
  `daytrader/proposal-*` branches, max one per ISO week. It never merges,
  never deploys, never restarts services, and its evidence gate
  (`analyst.min_labeled_events_week`) stays enforced in code, not just in
  the prompt. Deployment is weekly and human: merge → pull → restart.

## Common tasks

- **"Why no alert?"** → check `daytrader.db`: `alert_log` (dedupe hit?),
  `zone_events` (touch recorded but `confidence < scorer.min_confidence_alert`?),
  then logs for `touch suppressed`. Also confirm the webhook env var is set.
- **Add a ticker** → `config.yaml: tickers` + a `round_number_step` entry.
  Then re-seed: `python -m daytrader.backtest --start <6mo ago> --end <today>
  --tickers NEW --commit`.
- **Add a level type** → add to `SUPPORT_TYPES`/`RESIST_TYPES` and
  `reference_levels()`; calibration picks it up automatically after one
  nightly run. Give it ≥ 20 samples before trusting its quantiles.
- **Tune alert volume** → `scorer.min_confidence_alert` (up = quieter) and
  `levels.zone_max_atr_distance` (down = fewer, closer zones).
- **Validate any strategy change** → rerun the backtest over the last 6 months
  BEFORE and AFTER the change; paste both per-level tables in the PR/summary.

## Runbook

```bash
python -m daytrader.backtest --start 2025-01-02 --end <today> --commit  # seed
python -m daytrader.main                                                # run
python -m daytrader.backtest --start <3mo ago> --end <today>            # health check
```

DB: `daytrader.db` (tables: zone_events, sweep_samples, calibration,
alert_log). Model: `models/daytrader_scorer.pkl`. Scheduler times in
`config.yaml: alerts`, all US/Eastern.
