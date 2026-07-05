"""scorer.py — zone-touch confidence: rule-based cold start → Random Forest.

Every zone touch is a labeled sample whether or not anyone trades it, so this
converges far faster than a fill-gated learner (SnipeBot's bottleneck).
"""

import logging
import os
import pickle
from typing import Dict, List, Optional

import numpy as np

from daytrader import store
from daytrader.settings import CONFIG

logger = logging.getLogger(__name__)

_S = CONFIG["scorer"]
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_PATH = os.path.join(_BASE, _S["model_path"])

FEATURES: List[str] = [
    "sweep_depth_vs_q50",   # measured sweep depth / calibrated median
    "rvol",
    "session_minute",       # minutes since 09:30
    "vwap_dist_atr",        # (price - vwap)/ATR, signed with direction
    "respect_prior",        # historical respect rate for this level type
    "confluence",
    "is_long",
]


def build_features(ev: Dict, q50: float) -> np.ndarray:
    depth = float(ev.get("sweep_depth") or 0.0)
    return np.array([
        depth / q50 if q50 else 0.0,
        float(ev.get("rvol") or 1.0),
        float(ev.get("session_minute") or 0),
        float(ev.get("vwap_dist_atr") or 0.0),
        float(ev["respect_prior"]) if ev.get("respect_prior") is not None else 0.5,
        float(ev.get("confluence") or 1),
        1.0 if ev.get("direction") == "long" else 0.0,
    ], dtype=np.float32)


def heuristic_score(ev: Dict, q50: float) -> float:
    """Cold-start rules — mirrors the SnipeBot pattern."""
    p = 0.50
    depth = float(ev.get("sweep_depth") or 0.0)
    if q50 and 0.5 * q50 <= depth <= 1.8 * q50:
        p += 0.10                         # sweep ran a *typical* hunt depth
    elif depth > 3 * q50 if q50 else False:
        p -= 0.08                         # level truly broke, not swept
    if float(ev.get("rvol") or 1.0) >= 1.5:
        p += 0.08
    m = float(ev.get("session_minute") or 0)
    if 15 <= m <= 150 or 240 <= m <= 360:
        p += 0.07                         # avoid open shakeout + lunch chop
    v = float(ev.get("vwap_dist_atr") or 0.0)
    if (ev.get("direction") == "long" and v > 0) or \
       (ev.get("direction") == "short" and v < 0):
        p += 0.05                         # with-trend vs VWAP
    rp = ev.get("respect_prior")
    if rp is not None:
        p += max(-0.10, min(0.10, (float(rp) - 0.5) * 0.4))
    if int(ev.get("confluence") or 1) >= 2:
        p += 0.05
    return float(min(0.95, max(0.05, p)))


def _load_model():
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception as exc:
            logger.warning("model load failed: %s", exc)
    return None


def train_model() -> Optional[float]:
    """Weekly retrain from all labeled zone events. Returns holdout accuracy."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split

    events = store.labeled_events()
    if len(events) < int(_S["cold_start_events"]):
        logger.info("train skipped: %d labeled < %d",
                    len(events), _S["cold_start_events"])
        return None
    X, y = [], []
    for ev in events:
        ev = dict(ev)
        ev["respect_prior"] = None        # avoid target leakage at train time
        q50 = float(CONFIG["calibration"]["default_q50"])
        X.append(build_features(ev, q50))
        y.append(1 if ev["outcome"] == "win" else 0)
    X, y = np.vstack(X), np.asarray(y)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25,
                                          shuffle=False)   # time-ordered split
    clf = RandomForestClassifier(n_estimators=250, min_samples_leaf=5,
                                 class_weight="balanced", random_state=42)
    clf.fit(Xtr, ytr)
    acc = float(clf.score(Xte, yte))
    os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)
    import json
    from datetime import datetime, timezone
    with open(os.path.join(os.path.dirname(_MODEL_PATH),
                           "last_retrain.json"), "w") as f:
        json.dump({"holdout_acc": acc, "n_events": int(len(y)),
                   "trained_at": datetime.now(timezone.utc).isoformat()}, f)
    logger.info("scorer retrained on %d events, holdout acc %.3f", len(y), acc)
    return acc


def get_confidence(ev: Dict, q50: float) -> float:
    if store.count_labeled() < int(_S["cold_start_events"]):
        return heuristic_score(ev, q50)
    model = _load_model()
    if model is None:
        return heuristic_score(ev, q50)
    proba = float(model.predict_proba(build_features(ev, q50).reshape(1, -1))[0, 1])
    return round(proba, 4)
