"""levels_engine.py — reference levels → calibrated zones → alert table.

Pure functions: everything takes DataFrames + a calibration dict so the same
code path serves the live loop AND the walk-forward backtest (no divergence).

The anti-textbook idea: entry zones are NOT drawn at the obvious level. The
zone extends from the level down to the *measured median stop-hunt depth*
(q50), and the stop sits beyond the 90th-percentile overshoot (q90) — outside
where sweeps statistically exhaust for that ticker + level type.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from daytrader.settings import CONFIG

logger = logging.getLogger(__name__)

_L = CONFIG["levels"]
_C = CONFIG["calibration"]

SUPPORT_TYPES = ["PDL", "PML", "OPEN", "LOD", "RN_BELOW", "VWAP"]
RESIST_TYPES = ["PDH", "PMH", "HOD", "RN_ABOVE", "VWAP"]


# ── indicators ────────────────────────────────────────────────────────────────

def resample_5m(df_1m_rth: pd.DataFrame) -> pd.DataFrame:
    if df_1m_rth.empty:
        return df_1m_rth
    return (df_1m_rth.resample("5min")
            .agg({"open": "first", "high": "max", "low": "min",
                  "close": "last", "volume": "sum"})
            .dropna())


def compute_atr(df: pd.DataFrame, period: int = None) -> float:
    period = period or int(_L["atr_period"])
    if len(df) < 2:
        return float((df["high"] - df["low"]).mean() or 0.0)
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(span=min(period, len(df)), adjust=False).mean().iloc[-1])


def compute_rvol(df_1m_rth: pd.DataFrame, window: int = 20) -> float:
    vol = df_1m_rth["volume"].astype(float)
    if len(vol) < window + 1:
        return 1.0
    avg = vol.iloc[-window - 1:-1].mean()
    return round(float(vol.iloc[-1]) / avg, 3) if avg else 1.0


# ── reference levels ──────────────────────────────────────────────────────────

def reference_levels(ticker: str, price: float,
                     rth: pd.DataFrame, premarket: pd.DataFrame,
                     pd_hlc: Optional[tuple]) -> Dict[str, float]:
    refs: Dict[str, float] = {}
    if pd_hlc:
        refs["PDH"], refs["PDL"], refs["PDC"] = pd_hlc
    if not premarket.empty:
        refs["PMH"] = float(premarket["high"].max())
        refs["PML"] = float(premarket["low"].min())
    if not rth.empty:
        refs["OPEN"] = float(rth["open"].iloc[0])
        refs["HOD"] = float(rth["high"].max())
        refs["LOD"] = float(rth["low"].min())
        from daytrader.data_feed import cumulative_vwap
        v = cumulative_vwap(rth)
        if v:
            refs["VWAP"] = round(v, 2)
    step = float(_L["round_number_step"].get(ticker,
                 _L["round_number_step"]["default"]))
    refs["RN_BELOW"] = math.floor(price / step) * step
    refs["RN_ABOVE"] = math.ceil(price / step) * step
    return {k: round(v, 4) for k, v in refs.items()}


def _q(calib: Dict[str, Dict], level_type: str) -> tuple:
    row = calib.get(level_type) or {}
    n = row.get("n_samples", 0) or 0
    if n >= int(_C["min_samples_for_quantiles"]):
        return float(row["q50"]), float(row["q90"]), row.get("respect_rate")
    return float(_C["default_q50"]), float(_C["default_q90"]), row.get("respect_rate")


# ── zone construction ─────────────────────────────────────────────────────────

@dataclass
class Zone:
    ticker: str
    direction: str            # 'long' (demand) | 'short' (supply)
    level_type: str
    level: float
    zone_top: float
    zone_bottom: float
    stop: float
    target1: float
    target2: float
    confluence: int = 1
    respect_rate: Optional[float] = None
    members: List[str] = field(default_factory=list)


def _merge_confluent(cands: List[tuple]) -> List[tuple]:
    """cands: [(level_type, price)] → merged, keeping strongest type name."""
    tol = float(_L["confluence_tolerance"])
    merged: List[dict] = []
    for lt, px in sorted(cands, key=lambda x: x[1]):
        hit = next((m for m in merged if abs(m["px"] - px) / px <= tol), None)
        if hit:
            hit["members"].append(lt)
        else:
            merged.append({"px": px, "members": [lt]})
    return [(m["members"][0], m["px"], m["members"]) for m in merged]


def build_zones(ticker: str, price: float, atr: float,
                refs: Dict[str, float], calib: Dict[str, Dict]) -> List[Zone]:
    """Demand zone below price + supply zone above, calibrated by quantiles."""
    if atr <= 0 or price <= 0:
        return []
    max_dist = float(_L["zone_max_atr_distance"]) * atr
    zones: List[Zone] = []

    sup = [(lt, refs[lt]) for lt in SUPPORT_TYPES
           if lt in refs and 0 < price - refs[lt] <= max_dist]
    res = [(lt, refs[lt]) for lt in RESIST_TYPES
           if lt in refs and 0 < refs[lt] - price <= max_dist]

    for side, cands in (("long", sup), ("short", res)):
        if not cands:
            continue
        merged = _merge_confluent(cands)
        # prefer max confluence, then proximity to price
        merged.sort(key=lambda m: (-len(m[2]), abs(m[1] - price)))
        lt, lvl, members = merged[0]
        q50, q90, respect = _q(calib, lt)
        buf = float(_L["stop_buffer_atr"]) * atr
        if side == "long":
            top, bot = lvl, lvl * (1 - q50)
            stop = lvl * (1 - q90) - buf
            mid = (top + bot) / 2
            t1 = round(mid + float(_L["target1_atr"]) * atr, 2)
            t2 = round(mid + float(_L["target2_atr"]) * atr, 2)
            hod = refs.get("HOD")
            if hod and mid < hod < t1:      # snap T1 to overhead structure
                t1 = round(hod, 2)
        else:
            top, bot = lvl * (1 + q50), lvl
            stop = lvl * (1 + q90) + buf
            mid = (top + bot) / 2
            t1 = round(mid - float(_L["target1_atr"]) * atr, 2)
            t2 = round(mid - float(_L["target2_atr"]) * atr, 2)
            lod = refs.get("LOD")
            if lod and t1 < lod < mid:
                t1 = round(lod, 2)
        zones.append(Zone(
            ticker=ticker, direction=side, level_type=lt, level=round(lvl, 2),
            zone_top=round(top, 2), zone_bottom=round(bot, 2),
            stop=round(stop, 2), target1=t1, target2=t2,
            confluence=len(members), respect_rate=respect, members=members,
        ))
    return zones


# ── intraday sweep detection (arming signal) ──────────────────────────────────

def sweep_reclaim(df_1m: pd.DataFrame, level: float, side: str,
                  reclaim_bars: int = None) -> Optional[float]:
    """If a recent wick pierced `level` and price reclaimed it, return the
    overshoot fraction; else None. side: 'support' | 'resistance'."""
    reclaim_bars = reclaim_bars or int(_C["reclaim_bars"])
    recent = df_1m.iloc[-(reclaim_bars + 5):]
    if recent.empty:
        return None
    if side == "support":
        pierced = recent[recent["low"] < level]
        if pierced.empty or recent["close"].iloc[-1] <= level:
            return None
        return float((level - pierced["low"].min()) / level)
    pierced = recent[recent["high"] > level]
    if pierced.empty or recent["close"].iloc[-1] >= level:
        return None
    return float((pierced["high"].max() - level) / level)


# ── the alert table (matches the user's format) ───────────────────────────────

def levels_table(price: float, refs: Dict[str, float],
                 zone: Optional[Zone]) -> List[Dict[str, str]]:
    rows: List[tuple] = []
    if zone and zone.direction == "long":
        rows += [
            (zone.target2, "Target 2", "0DTE call target / extension"),
            (zone.target1, "Target 1", "0DTE call target / near HOD"),
        ]
    if "HOD" in refs:
        rows.append((refs["HOD"], "HOD", "Current high / first resistance"))
    rows.append((price, "Current", "Live price"))
    if zone and zone.direction == "long":
        conf = f" ({'+'.join(zone.members)})" if zone.confluence > 1 else ""
        rr = f" | respects {zone.respect_rate:.0%}" if zone.respect_rate else ""
        rows += [
            (zone.zone_top, "Entry Zone Top", f"Wait for pullback here{conf}"),
            (zone.zone_bottom, "Entry Zone Bottom",
             f"Demand / call entry zone{rr}"),
            (zone.stop, "Stop", "Invalidation — below = no trade"),
        ]
    if "OPEN" in refs:
        rows.append((refs["OPEN"], "Session Open", "Key intraday support"))
    if "VWAP" in refs:
        rows.append((refs["VWAP"], "VWAP", "Intraday mean / bias line"))
    rows.sort(key=lambda r: -r[0])
    seen, out = set(), []
    for px, typ, note in rows:
        if typ in seen:
            continue
        seen.add(typ)
        out.append({"level": f"${px:,.2f}", "type": typ, "notes": note})
    return out


def render_table(rows: List[Dict[str, str]]) -> str:
    w0 = max(len(r["level"]) for r in rows)
    w1 = max(len(r["type"]) for r in rows)
    lines = [f"| {'Level'.ljust(w0)} | {'Type'.ljust(w1)} | Notes",
             f"|{'-' * (w0 + 2)}|{'-' * (w1 + 2)}|------"]
    for r in rows:
        lines.append(f"| {r['level'].ljust(w0)} | {r['type'].ljust(w1)} | {r['notes']}")
    return "\n".join(lines)
