# Validation — how to know if anything actually works

Read this before ANY backtest, model change, or "it works" claim.
The core enemy is self-deception: leakage, overfitting, and small samples
produce beautiful equity curves that are pure fiction.

## 1. Event-based sampling and triple-barrier labels

- Sample on **events** (zone touches, triggers), not on every bar — bars are
  autocorrelated filler; events are the decisions.
- Label each event with the **triple-barrier method** (López de Prado): from
  the event, place an upper barrier (target), a lower barrier (stop), and a
  vertical barrier (time limit). The label is whichever is hit FIRST along the
  path — this encodes path dependence (a trade that hit the stop before the
  target is a loss even if price later flew).
- Barriers should be **volatility-scaled** (ATR / measured overshoot
  quantiles), not fixed percentages, so labels mean the same thing in calm
  and wild regimes.
- Conservative conventions: both barriers inside one bar → loss; timeouts are
  their own class (a high timeout rate means the time barrier or targets are
  mis-set — an audit finding, not noise).
- Record MFE/MAE per event; they diagnose whether targets/stops sit in the
  right place independent of the win/loss label.

## 2. Meta-labeling (the modern division of labor)

Primary model/rule proposes side + setup (e.g., sweep-reclaim long).
A **secondary (meta) model** learns, from labeled history, the probability
that acting on this primary signal ends well — and gates/sizes the action.
Benefits: the primary stays simple and interpretable; the meta-model absorbs
regime/context (session minute, RVOL, sweep depth vs q50, VWAP side,
confluence); precision improves without inventing new entry logic. This is
exactly the `scorer.py` role — keep it that way; don't let the meta-model
become the entry signal.

## 3. Leakage control: walk-forward vs purged CV

- Trading labels **overlap in time** (an event's label depends on the next N
  minutes). Naive k-fold CV therefore trains on information from the test
  window → optimistic garbage.
- **Walk-forward** (train on past → test on next block, roll) is the minimum
  standard and matches deployment reality. Its weakness: one test path,
  high variance in the estimate.
- **Purged k-fold + embargo** (López de Prado): drop training samples whose
  label windows overlap the test fold (purge) and skip a buffer after the
  test fold (embargo) to kill serial-correlation leakage. Combinatorial
  purged CV (CPCV) generates many train/test paths for distribution-level
  performance estimates — use for model selection when compute allows.
- Whatever the scheme: **calibration data must also be point-in-time** (day
  D's zones from quantiles learned on days < D; fold today's overshoots in
  only after simulating today). A leaked calibration is leakage all the same.

## 4. Sample-size math (the gate that kills most ideas honestly)

Standard error of a win rate ≈ √(p(1−p)/n). Consequences:

| n (labeled) | 95% CI half-width around p≈0.55 |
|---|---|
| 30 | ±17.8 pp — anecdote |
| 50 | ±13.8 pp — anecdote |
| 100 | ±9.8 pp — a 55% observed rate is indistinguishable from a coin |
| 385 | ±5.0 pp — first time 55% separates from 50% at 95% |
| 1000 | ±3.1 pp — respectable |

Rules derived from this:
- Minimum gates: ~30 labels to *look*, ~100 to *tune*, ~300+ to *believe*.
- **Parameter budget**: ≤1 free parameter per ~30–50 labeled events; a
  6-parameter setup "validated" on 80 trades is memorized noise.
- Expectancy > win rate: report avg R and its dispersion; a 40%-win,
  2.5R-payoff setup beats a 60%-win, 0.6R one.
- Judge NET of costs: spread (enter at ask), fees, slippage assumptions
  stated explicitly.

## 5. Deflate what search discovered

If a configuration was found by trying many variants, its backtest is biased
upward by selection. Bailey & López de Prado formalized this (probability of
backtest overfitting; deflated Sharpe ratio): the more combinations tried,
the higher the performance bar must be. Practical protocol:
- Log every variant tried (the analyst/PR history is this log).
- Hold out a final untouched period; the chosen variant must work there.
- Prefer fewer, hypothesis-first experiments over parameter sweeps.
- Treat a marginal improvement discovered after a long search as zero.

## 6. Live monitoring and decay

- Track rolling live win rate / expectancy per playbook vs its backtest
  confidence band; alert when outside the band for ≥30 consecutive events.
- Compare alerted vs suppressed outcomes weekly: if suppressed events out-
  perform alerted ones, the meta-model is miscalibrated — retrain/inspect.
- Track model holdout accuracy across retrains; monotone decay = features no
  longer describe the regime.
- Quarterly: full walk-forward re-run vs the original baseline. Material
  decay ⇒ the regime moved: revisit hypotheses (market-structure.md), don't
  just re-tune thresholds on the same data.
- Kill criteria are decided in advance (e.g., "retire the playbook if
  expectancy < 0 over the trailing 100 labeled events") — deciding after
  seeing the drawdown is how losing systems survive.

## 7. Pre-ship checklist (paste into any strategy-change PR)

- [ ] Hypothesis stated; regime filter + session window declared
- [ ] Labels: triple-barrier, vol-scaled, conservative conventions
- [ ] Point-in-time calibration & features (no `as_of` violations)
- [ ] Walk-forward tables: per ticker, per level/setup, per regime
- [ ] n per cell ≥ gate; parameter budget respected
- [ ] Net-of-cost expectancy positive with stated cost model
- [ ] Held-out final period untouched until the end — and passed
- [ ] Kill criteria written down
