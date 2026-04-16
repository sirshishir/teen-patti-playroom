"""
confidence_model.py — Random Forest classifier for trade confidence scoring.

Cold-start (<50 trades): uses rule-based weighted score from feature_engineer.py
Post cold-start:          uses trained RandomForestClassifier
Model persisted to:       models/confidence_model.pkl
"""

import logging
import os
import pickle
from typing import Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from ml.feature_engineer import (
    build_feature_vector, build_training_dataset, rule_based_confidence,
    FEATURE_NAMES,
)

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_MODEL_PATH = os.path.join(_BASE_DIR, "models", "confidence_model.pkl")
_COLD_START_THRESHOLD = 50  # configurable via config.yaml; loaded lazily

# In-memory model cache
_model: Optional[RandomForestClassifier] = None
_model_loaded = False


def _load_config_threshold() -> int:
    import yaml
    cfg_path = os.path.join(_BASE_DIR, "config.yaml")
    try:
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        return int(cfg["ml"]["cold_start_trades"])
    except Exception:
        return _COLD_START_THRESHOLD


def load_model() -> Optional[RandomForestClassifier]:
    """Load the persisted model from disk; return None if not found."""
    global _model, _model_loaded
    if _model_loaded:
        return _model
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                _model = pickle.load(f)
            logger.info("Confidence model loaded from %s", _MODEL_PATH)
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            _model = None
    else:
        _model = None
    _model_loaded = True
    return _model


def save_model(model: RandomForestClassifier) -> None:
    """Persist *model* to disk and update in-memory cache."""
    global _model, _model_loaded
    os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    _model = model
    _model_loaded = True
    logger.info("Confidence model saved to %s", _MODEL_PATH)


def train_model(trades) -> Optional[RandomForestClassifier]:
    """
    Train a new Random Forest on *trades* (list of dicts or sqlite3.Row).
    Returns trained model or None if insufficient data.
    """
    X, y = build_training_dataset(trades)
    if X.shape[0] < 20:
        logger.warning("Not enough training samples (%d) — skipping retrain", X.shape[0])
        return None

    # 80/20 train/val split
    if X.shape[0] >= 40:
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if y.sum() > 1 else None
        )
    else:
        X_train, X_val, y_train, y_val = X, X, y, y

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    val_acc = accuracy_score(y_val, clf.predict(X_val))
    logger.info("Model trained on %d samples. Validation accuracy: %.2f%%",
                X_train.shape[0], val_acc * 100)

    save_model(clf)
    return clf


def get_confidence_score(indicators: dict, vix: float, direction: str,
                          signal_time=None) -> float:
    """
    Return a confidence score in [0, 1].

    If fewer than cold_start_threshold trades exist in the DB → rule-based.
    Otherwise → Random Forest predicted probability of class 1 (TP hit).
    """
    from data import database as db

    threshold = _load_config_threshold()
    n_trades = db.count_all_trades()

    if n_trades < threshold:
        score = rule_based_confidence(indicators, vix, direction)
        logger.debug("Cold-start confidence (n=%d): %.4f", n_trades, score)
        return score

    model = load_model()
    if model is None:
        # Model not yet trained even though we have enough trades — use rule-based
        logger.warning("Model not found despite %d trades — using rule-based", n_trades)
        return rule_based_confidence(indicators, vix, direction)

    feat = build_feature_vector(indicators, vix, signal_time)
    prob = model.predict_proba(feat.reshape(1, -1))
    # prob shape: (1, n_classes); class order matches model.classes_
    classes = list(model.classes_)
    if 1 in classes:
        win_prob = float(prob[0][classes.index(1)])
    else:
        win_prob = 0.0

    logger.debug("RF confidence (n=%d): %.4f", n_trades, win_prob)
    return round(win_prob, 4)


def get_model_validation_accuracy() -> Optional[float]:
    """Quick accuracy estimate on all historical trades for the weekly report."""
    from data import database as db
    model = load_model()
    if model is None:
        return None
    trades = db.get_all_closed_trades()
    if not trades:
        return None
    X, y = build_training_dataset(trades)
    if X.shape[0] == 0:
        return None
    preds = model.predict(X)
    return round(float(accuracy_score(y, preds)) * 100, 1)
