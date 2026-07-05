---
name: day-trade-methodology
description: The modern, adaptive, evidence-based day-trading doctrine that supersedes classical textbook technical analysis. Consult this skill BEFORE designing, critiquing, tuning, or implementing ANY intraday trading logic — levels, zones, entries, stops, targets, breakouts, scanners, alert rules, indicators, backtests, ML labeling, or position sizing. Trigger it whenever the user mentions day trading, scalping, 0DTE, SMC/ICT, support/resistance, order blocks, liquidity sweeps, VWAP, opening range, win rates, "should this setup fire", or asks why a trade/alert worked or failed — even casually. If a request smuggles in a textbook assumption (fixed 2:1 RR, RSI oversold = buy, stop just below support), this skill defines how to respond. Companion to the `day-trader` skill (which covers the codebase); this one covers the trading brain.
---

# Day-Trade Methodology — the adaptive doctrine

## 0. Why this skill exists

Classical retail day trading, executed as taught, is a statistically losing
activity. The evidence is consistent across markets and decades:

- Brazil equity futures (Chague, De-Losso & Giovannetti 2020): of everyone who
  began day trading 2013–2015 and persisted 300+ sessions, **97% lost money**;
  only 1.1% out-earned minimum wage; the study found **no evidence of learning
  by trading**.
- Taiwan, 15 years of complete market data (Barber, Lee, Liu & Odean): **under
  1%** of day traders earn predictably positive returns net of fees; on a given
  day ~97% of day traders lose after costs; past losses barely reduce
  re-participation (overconfidence, not skill acquisition).
- US (Jordan & Diltz 2003): 64% lost money **during a raging bull market**.
  Barber & Odean (2000): the most active retail quintile underperformed by
  ~6.5 pp/year.

The failure is not random — it is structural. The textbook itself is the
problem: when everyone learns to put stops just below the same obvious support,
those stops become the resting liquidity that larger participants trade *into*.
Textbook behavior is the exhaust that modern flows feed on.

Therefore the prime directive: **never implement a textbook rule as-is.
Replace it with its measured, regime-conditional, validated counterpart —
and require statistical evidence before anything fires live.**

## 1. The Replacement Table (textbook → modern adaptive)

| # | Classical textbook | Modern adaptive replacement |
|---|---|---|
| 1 | Draw S/R at the obvious swing/round number; enter AT the level | Treat the obvious level as a **liquidity magnet**, not a wall. Entry zone extends from the level to the *measured median stop-hunt overshoot* (q50) for that ticker + level type; expect the wick through the level. |
| 2 | Stop "just below support" | Stop beyond the **90th-percentile measured overshoot (q90) + volatility buffer** — outside where sweeps statistically exhaust. If the resulting risk is too large, skip the trade; never tighten into the hunt zone. |
| 3 | Fixed 2:1 risk-reward, round-number targets | Volatility-scaled targets (ATR multiples) **snapped to structure** (HOD/LOD, prior value area, high-gamma strikes). Judge setups by measured expectancy per touch, not by the RR you drew. |
| 4 | RSI < 30 = buy, MACD cross = signal | Indicators are **features, never triggers**. Any indicator enters only as an input to a scored, validated model; standalone oscillator rules are noise with costs. |
| 5 | Chart patterns (H&S, flags, triangles) as predictions | The **auction framework**: is the market in balance (rotational, mean-reverting) or imbalance (one-time-framing trend)? Patterns are re-described as balance/imbalance transitions and only traded with a regime filter. |
| 6 | Trade all day, every day | **Session-time edge map.** Volume and volatility are U-shaped (Andersen & Bollerslev); the first half-hour digests overnight information; midday is chop; the last half-hour is rebalancing + hedging flow. Gao–Han–Li–Zhou (JFE 2018): the first half-hour return predicts the last half-hour return. Each playbook declares *when* it is allowed to fire. |
| 7 | Same parameters forever | **Rolling recalibration.** Overshoot quantiles, respect rates, and model weights refresh on a rolling window (nightly/weekly); a strategy version is re-validated walk-forward before deploy; quarterly decay checks kill stale setups. |
| 8 | "Price action" storytelling | **Positioning mechanics.** Explain moves via who is forced to transact: dealer gamma hedging (0DTE is now ~59–60% of SPX options volume; positive gamma → pinning/mean reversion toward high-GEX strikes, negative gamma → amplification), VWAP-benchmarked institutional execution, stop clusters, MOC/charm flows into the close. Mag7 names (incl. GOOGL, TSLA) gained Mon/Wed expiries in early 2026 — gamma mechanics now bind single names most of the week, not just Fridays. |
| 9 | Confidence from conviction/gut | **Probabilistic scoring.** Every signal carries a calibrated probability from measured base rates (respect rates, meta-model output). Below threshold → record the event for learning, do not act/alert. |
| 10 | Backtest = one pretty equity curve | **Labeling + leakage discipline.** Triple-barrier labels (path-dependent: which barrier hit first), walk-forward or purged/embargoed CV (labels overlap in time → naive k-fold leaks), minimum sample gates, and deflated expectations for anything discovered by search (Bailey/López de Prado: probability of backtest overfitting). |
| 11 | Enter at mid, ignore costs | Price entries at the **ask**, model the spread, refuse wide-spread contracts, and subtract realistic costs from every expectancy figure. Costs are why most "profitable" retail systems lose. |
| 12 | Add rules when losing | **Parameter budget.** Every free parameter must be paid for with samples (rule of thumb: ≥30–50 labeled events per parameter). More rules on the same data = memorizing noise. |

## 2. The Adaptive Loop (non-negotiable operating rhythm)

1. **Measure** — record *every* setup occurrence (touch/trigger), traded or
   not, alerted or suppressed. Untraded occurrences are free training data;
   fill-gated learning starves.
2. **Label** — nightly, triple-barrier each occurrence on true consolidated
   (SIP) 1-minute data: win / loss / timeout, minutes-to-outcome, MFE/MAE.
   Both-barriers-in-one-bar resolves as loss (conservative).
3. **Calibrate** — nightly, refresh per-ticker, per-level-type overshoot
   quantiles (q50/q90) and respect rates on a rolling window (~90 sessions).
   Tomorrow's zones are drawn from tonight's distributions.
4. **Score** — weekly, retrain the meta-model (e.g., RandomForest) on all
   labeled events with a time-ordered split; below the cold-start sample count,
   use the documented heuristic. The meta-model's job is meta-labeling: decide
   *whether/how much* to act on a primary signal, not to predict the market.
5. **Validate** — before any logic/parameter change ships: walk-forward
   backtest, before-vs-after tables, per-setup n and expectancy. No table, no
   merge.
6. **Audit** — weekly analyst review: label-quality issues (timeout rate too
   high → wrong time barrier), alerted-vs-suppressed performance gap, holdout
   accuracy drift, regime shifts. Proposer, never operator.
7. **Decay-check** — quarterly full re-run vs the original baseline. If
   expectancy decayed materially, the regime moved: rework, don't re-tune.

**Data discipline underneath everything:** consolidated tape (SIP) for
anything that touches wicks or volume; completed bars only for signal
evaluation (partial bars repaint); split/dividend-adjusted series;
point-in-time features (no future rows, `as_of` everywhere in backtests);
timezone-anchored session bars (09:30 ET).

## 3. Regime First — no playbook without a filter

Before any setup is considered, classify the tape. The same trigger has
opposite expectancy in different regimes.

- **Volatility regime**: realized-vol / VIX buckets (low / normal / elevated /
  crisis). Zone widths, stops, and targets all scale with it; in crisis
  regimes most mean-reversion playbooks are OFF.
- **Gamma regime** (index + single name where near-daily expiries exist):
  net-positive dealer gamma → mean reversion, strike pinning, fade extremes;
  net-negative → moves amplify, breakouts run, fading is forbidden. The gamma
  flip level is an intraday pivot. GEX resets daily now that 0DTE dominates —
  yesterday's map is stale by the open.
- **Day type**: classify the open by ~10:00–10:30 (open-drive vs
  open-auction/rotation, gap size vs ATR, one-sidedness of early volume).
  Trend days forbid fading and demand pullback-only entries; balance days
  favor edge-fading toward VWAP/POC.
- **Calendar**: FOMC/CPI/NFP days, OPEX, month-end — different animals.
  Pre-event compression is not a breakout setup; post-event, stand aside for
  the first bars, then trade the *reaction*, not the print.

## 4. Risk canon (applies to every playbook)

- Fixed fractional risk per trade (small); position size = risk ÷ stop
  distance, so wider calibrated stops mean smaller size, never wider risk.
- Daily loss circuit breaker: hit it → flat and done; no revenge sizing.
- Never average into an invalidated thesis; invalidation = 1-min close beyond
  the calibrated stop, not a feeling.
- Respect account-structure constraints (e.g., US PDT rules under $25k).
- For options expressions: buy at ask, cap spread %, size for premium-to-zero,
  and remember 0DTE gamma/theta make afternoon errors non-linear.
- Alerts-first development: a strategy earns real capital only after surviving
  the full validation ritual on recorded live-alert data.

## 5. How the agent should behave with this skill

- When asked to add a textbook rule ("alert when RSI < 30"): don't refuse,
  **upgrade** — implement it as a feature + backtest it through the standard
  ritual, and report whether it earns its parameter budget.
- When asked "why did the alert fail?": answer with mechanics (regime, sweep
  depth vs calibration, gamma state, session time) and the labeled outcome
  data — not narratives.
- When proposing changes: one hypothesis at a time, evidence gates stated,
  before/after walk-forward tables attached, config-only unless the human
  approves code changes.
- When evidence is thin (n below gate): say so, keep collecting, do not ship.
- Be honest about the base rates in §0 whenever a plan's risk profile expands.

## 6. Reference files (read on demand)

- `references/market-structure.md` — the session clock (ET) and U-shape,
  open types, intraday momentum effect, volume profile/value concepts, dealer
  gamma & 0DTE mechanics, stop-cluster/sweep mechanics. Read when reasoning
  about *why* price behaves a certain way intraday or designing time/regime
  filters.
- `references/playbooks.md` — six adaptive playbooks (calibrated sweep-reclaim,
  opening drive, VWAP reversion, trend-day protocol, last-half-hour momentum
  overlay, event-day protocol), each with hypothesis, regime filter, trigger,
  invalidation, targets, evidence gate, and failure modes. Read when adding or
  tuning a setup.
- `references/validation.md` — labeling (triple-barrier), meta-labeling,
  purged/embargoed CV vs walk-forward, sample-size math, deflated
  expectations, parameter budgets, decay monitoring. Read before ANY backtest,
  model change, or claim that something "works".

## 7. Mapping to the `daytrader` package (this repo)

- Replacement rows 1–2 → `levels_engine.build_zones` (q50/q90 zones);
  row 6 → scheduler windows + scorer session_minute feature;
  rows 9–10 → `scorer.py` + `calibrate.triple_barrier` + `backtest.py`
  (walk-forward); row 11 → ask-priced options in SnipeBot FIX-9.
- Every touch recorded even when suppressed = §2.1. Nightly job = §2.2–2.3.
  Weekly retrain = §2.4. Weekly analyst = §2.6. Quarterly re-run = §2.7.
- Gaps to close over time (candidate proposals, each through the ritual):
  gamma-regime feature (needs an options-positioning data source), day-type
  classifier at 10:30, first→last half-hour momentum overlay, event-calendar
  gating.
