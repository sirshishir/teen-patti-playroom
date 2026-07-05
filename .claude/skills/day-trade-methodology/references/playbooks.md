# Playbooks — adaptive setups (each earns its existence with data)

Format per playbook: **Hypothesis** (whose forced flow creates the edge) →
**Regime filter** → **Trigger** (measurable) → **Invalidation** → **Targets**
→ **Evidence gate** (before live alerts) → **Failure modes**.
A playbook without a regime filter or an evidence gate is a textbook rule in
costume — reject it.

## P1. Calibrated Sweep–Reclaim at Reference Levels (core)

- **Hypothesis**: stop clusters beyond PDH/PDL, session open, PM extremes,
  round numbers are harvested for fills; after the harvest, the initiating
  flow's direction reasserts.
- **Regime**: OFF in crisis vol; on trend days only WITH-trend side allowed;
  strongest on balance days and positive-gamma tape.
- **Trigger**: price enters the calibrated zone [level·(1−q50), level] (long
  case) after being outside; sweep depth within ~0.5–1.8× q50; reclaim close
  back across the level within the reclaim window; confluence (≥2 merged
  reference levels) is a confidence bonus.
- **Invalidation**: 1-min close beyond level·(1−q90) − vol buffer.
- **Targets**: T1 = zone mid + 1.5·ATR(5m) snapped to overhead structure
  (HOD / value edge / high-gamma strike); T2 = 2.5·ATR extension.
- **Evidence gate**: ≥30 labeled touches per ticker+level-type with respect
  rate meaningfully > 50% after costs; suppress alerts below the confidence
  threshold but record everything.
- **Failure modes**: depth ≫ q90 = repricing not sweep; lunch-hour sweeps
  under-follow-through; consumed levels (already closed through earlier)
  aren't pools anymore — invalidate them.

## P2. Opening Drive / Range Break (regime-gated ORB)

- **Hypothesis**: on genuine information days, the open is the start of an
  imbalance; early one-sided flow continues (left leg of the U carries the
  day's information).
- **Regime**: ONLY when gap ≥ ~0.75× day-ATR beyond prior range AND first
  30-min volume strongly one-sided AND tape reads negative-gamma/expansion.
  On balance days this playbook is OFF — that's where classic ORB dies.
- **Trigger**: break of the 30-min opening range in gap direction, on RVOL ≥
  1.5, with the retest holding above/below the range edge.
- **Invalidation**: close back inside the opening range.
- **Targets**: measured move (range height) then trail; no fixed cap on trend
  days.
- **Evidence gate**: ≥40 labeled instances; report win% AND payoff ratio —
  ORB is a low-win-rate/high-payoff shape, judge by expectancy only.
- **Failure modes**: firing it daily (most days are balance days → death by a
  thousand fakeouts); news at 10:00 reversing the drive; counting a
  premarket-drift gap as an information gap.

## P3. VWAP Mean Reversion (balance-day fade)

- **Hypothesis**: institutions benchmark to VWAP; in positive-gamma/balance
  tape, dealer hedging + benchmark execution pull extensions back to the mean.
- **Regime**: balance day + positive-gamma proxies + midday window
  (~11:00–14:30). OFF on trend days, event days, negative-gamma tape.
- **Trigger**: extension ≥ k·ATR from VWAP (calibrate k per ticker from the
  extension distribution) with momentum fading (declining RVOL on the push).
- **Invalidation**: extension continues one more ATR unit / new one-sided
  volume wave.
- **Targets**: VWAP (T1); opposite value edge (T2) only on strong rotation.
- **Evidence gate**: ≥40 labeled instances; verify midday-only subset
  separately (the edge usually lives there).
- **Failure modes**: fading a transition day that's becoming a trend day —
  the single most expensive mistake in this playbook; re-classify at 12:00.

## P4. Trend-Day Protocol (mostly a discipline, partly a setup)

- **Hypothesis**: on one-time-framing days, liquidity vacuums keep pullbacks
  shallow; the crowd fades all day and fuels the trend.
- **Regime detection (by ~10:30)**: open-drive from an extreme, gap holds,
  breadth/volume one-sided, pullbacks < 0.5 day-ATR, negative-gamma proxies.
- **Rules once detected**: all fade playbooks OFF; entries only on pullbacks
  to rising/falling short-MA / prior breakout shelf / VWAP-first-touch;
  stops beyond pullback swing + buffer; trail, never target-cap; last-hour
  charm/momentum usually extends, not reverses.
- **Evidence gate**: track classification precision — % of "trend by 10:30"
  calls that closed in the top/bottom quintile of their range; tune the
  classifier before trusting the protocol.
- **Failure modes**: late detection → chasing extension; treating FOMC-day
  afternoon as an organic trend.

## P5. Last-Half-Hour Momentum Overlay (15:30–16:00)

- **Hypothesis**: rebalancing, late-informed flow, MOC imbalances, and charm
  concentrate at the close; first-half-hour return sign predicts last-half-
  hour return (Gao et al. 2018), stronger on volatile/news days.
- **Use**: as a modifier, not a standalone: with-momentum continuation setups
  in the window get a confidence bonus; counter-momentum fades get penalized
  or blocked. Optionally a standalone signal ONLY after local validation on
  the traded tickers.
- **Invalidation/size**: micro stops don't survive closing tape — smaller
  size, structure-based stops, flat by 15:58 for alerts-only sanity.
- **Evidence gate**: ≥60 window-days measured per ticker (one observation per
  day makes n accrue slowly — be patient).
- **Failure modes**: OPEX/rebalance-date distortions; assuming a 1993–2013
  SPY effect transfers untested to single names.

## P6. Event-Day Protocol (FOMC / CPI / NFP / OPEX)

- **Hypothesis**: pre-event, books thin and ranges compress (not a breakout
  signal); the first post-release move is often the hunt, the second the
  trade; OPEX afternoons add pin-then-release dynamics.
- **Rules**: no new positions/alerts N minutes before scheduled releases
  (calendar-gate the scanner); post-release, stand aside 2–3 bars, then trade
  the *reaction* through P1 logic with event-day calibration (overshoots on
  event days come from a fatter distribution — calibrate them as their own
  bucket if n allows); OPEX: expect pinning to heavy strikes into the
  afternoon, expansion after.
- **Evidence gate**: event-day samples are rare — pool across tickers, keep a
  separate label bucket, and demand n ≥ 25 before any event-specific rule.
- **Failure modes**: trading the print itself; using normal-day quantiles on
  event days; forgetting that gamma maps rebuild intraday after the release.

## Adding a new playbook (checklist)

1. Write the hypothesis in one sentence naming the forced flow.
2. Declare the regime filter + session window it's allowed in.
3. Define trigger/invalidation/targets in measurable terms (no adjectives).
4. Set the evidence gate (n and expectancy threshold) BEFORE looking at data.
5. Walk-forward it; report per-regime tables; check the parameter budget
   (`references/validation.md`).
6. Ship alerts-only; re-evaluate at the gate; only then discuss capital.
