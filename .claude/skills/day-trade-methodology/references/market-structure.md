# Market Structure — why intraday price does what it does

Read this when designing time filters, regime filters, or explaining behavior.

## 1. The session clock (all times ET)

| Time | What happens | Implication |
|---|---|---|
| 04:00–09:30 | Premarket. Thin books; overnight news gets a first price. PMH/PML form. | Premarket extremes = early liquidity pools; gaps set the day's information load. |
| 08:30 | Major macro releases (CPI, NFP, etc.) print. | On release days the premarket range is event-driven; treat separately. |
| 09:30 | Opening auction. Session open prints. | Session open is a real institutional reference level, not decoration. |
| 09:30–10:00 | Left leg of the volume/volatility **U-shape** (Andersen & Bollerslev 1997): the market digests overnight information; widest ranges, most sweeps of premarket/prior-day levels. | First ~10 min: highest sweep frequency AND lowest signal quality. Most systems should observe, not trade, the first bars. |
| 10:00 | Second-tier econ data (ISM, sentiment, etc.). | A common reversal/extension trigger for the opening move. |
| ~10:30 | Enough structure exists to classify **day type** (see §2). | Regime filters switch on here. |
| ~11:30–13:30 | Lunch. Volume trough of the U. | Mean-reversion dominates; breakout playbooks OFF; false-break frequency peaks. |
| 14:00 | FOMC statement (8×/yr). | On those days, everything before 14:00 is positioning noise. |
| 15:00 | Bond futures close; hedging adjustments begin. | Vol often re-awakens. |
| 15:30–16:00 | Right leg of the U. MOC imbalances publish ~15:50; option **charm** (delta decay) forces continuous dealer re-hedging into expiry; late-informed and rebalancing flow concentrates. | Distinct micro-regime with its own playbook (see intraday momentum, §3). |
| 16:00 | Closing auction — the day's largest single liquidity event. | Marks/pins matter; single-print closes tell you who was trapped. |

## 2. Day types (classify by ~10:30, re-check at 12:00)

- **Trend day / open-drive**: opens near one extreme and one-time-frames away
  from it; gap doesn't fill early; early volume one-sided; pullbacks shallow
  (< ~0.5 day-ATR). Odds increase with a gap beyond the prior day's range that
  holds the first 30 min. Rules: fading is forbidden; entries are
  pullback-continuation only; targets trail, don't cap.
- **Balance / rotation day**: open inside prior value; early probes in both
  directions get responsive selling/buying; volume builds a symmetric profile.
  Rules: fade the edges toward VWAP/POC; breakout triggers demand extra
  confirmation (most range breaks on balance days fail — that failure IS the
  sweep-reclaim setup).
- **Transition day**: balance morning, imbalance afternoon (or reverse),
  usually catalyzed at a §1 clock point. Rule: re-classify at fixed
  checkpoints instead of anchoring to the morning's label.

## 3. Intraday momentum (documented, not folklore)

Gao, Han, Li & Zhou (JFE 2018), on decades of SPY high-frequency data: the
**first half-hour return (measured from the prior close) positively predicts
the last half-hour return**, and the effect strengthens on high-volatility,
high-volume, and macro-news days. Mechanisms offered: infrequent portfolio
rebalancing and late-informed trading pressed against the close; Baltussen,
Da, Lammers & Martens (JFE 2021) tie intraday momentum to hedging demand.

Use: as a *bias filter* for 15:30–16:00 — with-momentum setups get a
confidence bonus, counter-momentum fades get a penalty. Do not use it as a
standalone trigger; validate the effect on your tickers and window first
(effects published on 1993–2013 data must re-earn their place).

## 4. Dealer gamma and the 0DTE regime (the modern tape's spine)

- 0DTE contracts grew from a niche (daily SPX expiries listed 2022) to roughly
  **59–60% of SPX options volume by 2025**; in early 2026 Mon/Wed expiries were
  approved for Mag7-class single names (incl. GOOGL, TSLA) — so single-name
  gamma mechanics now operate most days of the week, not just Fridays.
- Mechanics: dealers hedge option books delta-neutral. **Net long gamma** →
  they buy dips / sell rips → volatility dampens, price mean-reverts and
  "pins" toward high-GEX strikes (usually round strikes — which is why round
  numbers pin harder than folklore alone explains). **Net short gamma** →
  hedging chases price → moves amplify, breakouts run, fades die.
- The **gamma flip** (net GEX zero-cross) behaves like an intraday pivot:
  above it expect rotation, below it expect trend/expansion.
- ATM gamma grows explosively as expiry approaches (several times a weekly's,
  spiking further near the close), so afternoon hedging flows dominate late
  tape; **charm** adds a steady directional drip into 16:00.
- 0DTE positioning **resets daily** — any GEX map from yesterday's snapshot is
  stale by the open. Gross volume ≠ net exposure: flows can offset; the effect
  is episodic and strongest when flow is one-sided and liquidity thin.
- Without a positioning feed, use behavioral proxies: repeated failed range
  extensions + reversion to a round strike ⇒ treat as positive-gamma tape;
  accelerating range expansion through prior extremes ⇒ negative-gamma tape.

## 5. Stop clusters and sweep mechanics (why "obvious" levels get run)

Large participants cannot fill size without counterparties. Clusters of
resting stops — just beyond swing highs/lows, PDH/PDL, session opens, round
numbers, premarket extremes — are *pre-packaged liquidity*: pushing price into
the cluster converts resting stops into market orders that fill the big
player's position, after which price frequently reverses. Consequences:

- The obvious level is the **target of the move, not the barrier** — expect
  the overshoot; measure its depth distribution per ticker + level type
  rather than guessing (this is exactly the q50/q90 calibration).
- Sweeps concentrate at session opens and immediately before/after scheduled
  news — when the excuse (volatility) and the need (fills) coincide.
- A *valid* sweep-reclaim shows displacement back inside within minutes and
  no follow-through beyond the q90 envelope; a level that keeps closing
  beyond is a genuine repricing, not a hunt — stand down.
- Defensive corollary: stops based on measured overshoot + volatility buffer
  sit outside the harvest zone; stops at "just below support" sit inside it.

## 6. Volume profile vocabulary (minimum useful set)

- **Value area (VA)**: price band holding ~70% of session volume; **POC**: the
  highest-volume price. Opens inside value → rotation odds up; opens outside
  value that fail to return → imbalance odds up.
- **Single prints / low-volume nodes**: fast-traversed prices; revisits move
  quickly through them (poor support, good targets).
- Prior day's VA/POC join PDH/PDL/PDC as reference levels worth calibrating —
  add as a level type only with its own sample gate.
