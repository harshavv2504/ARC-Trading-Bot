"""
Entry Timing Model — RandomForest binary classifier on 1-minute candles.

Answers: "Should I enter this option trade RIGHT NOW or wait?"

ENTER (1): Price likely to move > 0.4% in next 15 minutes (enough to profit on premium)
WAIT  (0): No momentum confluence — premium likely to bleed (theta + lack of move)

This is the final ML gate before sending a signal to the LLM.
Reduces LLM calls by rejecting entries with no momentum confirmation.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV

from backend.ml.features import (
    compute_features, label_entry_timing,
    TIMING_MODEL_FEATURES, MIN_ROWS,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_PATH = Path(__file__).parent / "models" / "timing_model.pkl"
THRESHOLD  = 0.60   # high precision threshold — we only enter when very confident


def build_training_data(
    onemin_data: dict[str, pd.DataFrame],
    sample_every: int = 2,
) -> tuple[pd.DataFrame, pd.Series]:
    frames = []
    for symbol, df in onemin_data.items():
        if len(df) < MIN_ROWS:
            continue
        df_feat = compute_features(df)
        df_feat["label_entry"] = label_entry_timing(df_feat, horizon=15, threshold_pct=0.4)
        df_feat = df_feat.dropna(subset=TIMING_MODEL_FEATURES + ["label_entry"])
        if len(df_feat) < MIN_ROWS:
            continue
        frames.append(df_feat.iloc[::sample_every][TIMING_MODEL_FEATURES + ["label_entry", "date"]])

    if not frames:
        raise ValueError("No usable 1-minute data for timing model")

    combined = pd.concat(frames, ignore_index=True).sort_values("date")
    X = combined[TIMING_MODEL_FEATURES].astype(float)
    y = combined["label_entry"].astype(int)

    enter_rate = y.mean()
    logger.info(f"Timing training set: {len(X):,} rows | ENTER rate: {enter_rate:.1%}")
    return X, y


def train(onemin_data: dict[str, pd.DataFrame]) -> "TimingModel":
    X, y = build_training_data(onemin_data)

    pos = int(y.sum())
    neg = int((y == 0).sum())
    spw = neg / max(pos, 1)

    # GBM: better at precision than RF for binary with imbalanced classes
    base = GradientBoostingClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=50,
        random_state=42,
    )

    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, val_idx = splits[-1]

    logger.info(f"Training timing model on {len(train_idx):,} rows…")
    base.fit(X.iloc[train_idx], y.iloc[train_idx])

    calibrated = CalibratedClassifierCV(base, cv="prefit", method="sigmoid")
    calibrated.fit(X.iloc[val_idx], y.iloc[val_idx])

    y_pred = (calibrated.predict_proba(X.iloc[val_idx])[:, 1] >= THRESHOLD).astype(int)
    y_prob = calibrated.predict_proba(X.iloc[val_idx])[:, 1]
    auc = roc_auc_score(y.iloc[val_idx], y_prob)

    logger.info(f"\nTiming Model Validation (AUC={auc:.3f}, threshold={THRESHOLD}):")
    logger.info("\n" + classification_report(y.iloc[val_idx], y_pred, target_names=["WAIT", "ENTER"]))

    model = TimingModel(calibrated, auc)
    model.save()
    return model


class TimingModel:
    def __init__(self, clf, auc: float = 0.0):
        self.clf = clf
        self.auc = auc

    def predict(self, df: pd.DataFrame) -> dict:
        """
        Classify entry timing from 1-min OHLCV candles.
        Returns {decision, probability, enter_now}.
        """
        if len(df) < MIN_ROWS:
            return {"decision": "WAIT", "probability": 0.0, "enter_now": False, "reason": "insufficient_data"}

        df_feat = compute_features(df)
        row = df_feat[TIMING_MODEL_FEATURES].dropna().tail(1)
        if row.empty:
            return {"decision": "WAIT", "probability": 0.0, "enter_now": False, "reason": "nan_features"}

        prob = float(self.clf.predict_proba(row)[0, 1])
        enter = prob >= THRESHOLD

        return {
            "decision":    "ENTER" if enter else "WAIT",
            "probability": round(prob, 3),
            "enter_now":   enter,
            "confidence":  "HIGH" if prob >= 0.75 else ("MODERATE" if prob >= THRESHOLD else "LOW"),
        }

    def save(self):
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, MODEL_PATH)
        logger.info(f"Timing model saved → {MODEL_PATH}")

    @classmethod
    def load(cls) -> "TimingModel":
        if not MODEL_PATH.exists():
            raise FileNotFoundError("Timing model not found. Run: python -m backend.ml.train")
        return joblib.load(MODEL_PATH)

    @classmethod
    def exists(cls) -> bool:
        return MODEL_PATH.exists()
