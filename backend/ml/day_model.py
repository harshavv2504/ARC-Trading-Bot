"""
Direction Classifier — XGBoost 5-class model.

Trained on NIFTY + BANKNIFTY daily OHLCV + VIX.
Predicts next-day index direction: STRONG_UP / UP / FLAT / DOWN / STRONG_DOWN

This feeds directly into options strategy selection:
  STRONG_UP   → Buy ATM CE (aggressive)
  UP          → Buy ATM or SLIGHTLY_OTM CE (moderate)
  FLAT        → Skip or wait
  DOWN        → Buy ATM or SLIGHTLY_OTM PE (moderate)
  STRONG_DOWN → Buy ATM PE (aggressive)
"""

from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report
from sklearn.preprocessing import LabelEncoder

from backend.ml.features import (
    compute_features, label_direction,
    DAY_MODEL_FEATURES, MIN_ROWS, DIRECTION_CLASSES,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_PATH = Path(__file__).parent / "models" / "day_model.pkl"


def build_training_data(
    daily_data: dict[str, pd.DataFrame],
    vix_series: pd.Series | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    frames = []
    for symbol, df in daily_data.items():
        if len(df) < MIN_ROWS:
            continue
        df_feat = compute_features(df, vix_series=vix_series)
        df_feat["label_direction"] = label_direction(df_feat, horizon=1, threshold_pct=0.5)
        df_feat = df_feat.dropna(subset=DAY_MODEL_FEATURES + ["label_direction"])
        if len(df_feat) < MIN_ROWS:
            continue
        frames.append(df_feat[DAY_MODEL_FEATURES + ["label_direction", "date"]])

    if not frames:
        raise ValueError("No usable daily data for training")

    combined = pd.concat(frames, ignore_index=True).sort_values("date")
    X = combined[DAY_MODEL_FEATURES].astype(float)
    y = combined["label_direction"]

    dist = y.value_counts(normalize=True)
    logger.info(f"Direction training set: {len(X):,} rows\n{dist.to_string()}")
    return X, y


def train(
    daily_data: dict[str, pd.DataFrame],
    vix_series: pd.Series | None = None,
) -> "DayModel":
    X, y = build_training_data(daily_data, vix_series)

    le = LabelEncoder()
    le.fit(DIRECTION_CLASSES)
    y_enc = le.transform(y)

    clf = XGBClassifier(
        n_estimators=600,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=10,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="multi:softprob",
        num_class=len(DIRECTION_CLASSES),
        eval_metric="mlogloss",
        early_stopping_rounds=40,
        random_state=42,
        verbosity=0,
        device="cpu",
    )

    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, val_idx = splits[-1]

    clf.fit(
        X.iloc[train_idx], y_enc[train_idx],
        eval_set=[(X.iloc[val_idx], y_enc[val_idx])],
        verbose=False,
    )

    y_pred = clf.predict(X.iloc[val_idx])
    logger.info(f"\nDirection Model Validation:")
    logger.info("\n" + classification_report(
        y_enc[val_idx], y_pred, target_names=le.classes_
    ))

    model = DayModel(clf, le)
    model.save()
    return model


class DayModel:
    def __init__(self, clf, encoder: LabelEncoder):
        self.clf     = clf
        self.encoder = encoder

    def predict(self, df: pd.DataFrame, vix_series: pd.Series | None = None) -> dict:
        """
        Predict direction from OHLCV candles.
        Returns {direction, probabilities, confidence, trade_side}.
        """
        if len(df) < MIN_ROWS:
            return _neutral_prediction("insufficient_data")

        df_feat = compute_features(df, vix_series=vix_series)
        row = df_feat[DAY_MODEL_FEATURES].dropna().tail(1)
        if row.empty:
            return _neutral_prediction("nan_features")

        probs = self.clf.predict_proba(row)[0]
        pred_idx = int(np.argmax(probs))
        direction = self.encoder.inverse_transform([pred_idx])[0]

        prob_dict = {
            cls: round(float(p), 3)
            for cls, p in zip(self.encoder.classes_, probs)
        }

        # For buy-side: compute bull vs bear probability
        bull_prob = prob_dict.get("STRONG_UP", 0) + prob_dict.get("UP", 0)
        bear_prob = prob_dict.get("STRONG_DOWN", 0) + prob_dict.get("DOWN", 0)

        trade_side = None
        if direction in ("STRONG_UP", "UP"):
            trade_side = "CE"
        elif direction in ("STRONG_DOWN", "DOWN"):
            trade_side = "PE"

        return {
            "direction": direction,
            "probabilities": prob_dict,
            "confidence": round(float(max(probs)), 3),
            "bull_prob": round(bull_prob, 3),
            "bear_prob": round(bear_prob, 3),
            "trade_side": trade_side,       # "CE" | "PE" | None
            "is_strong": direction in ("STRONG_UP", "STRONG_DOWN"),
        }

    def save(self):
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, MODEL_PATH)
        logger.info(f"Day model saved → {MODEL_PATH}")

    @classmethod
    def load(cls) -> "DayModel":
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Day model not found. Run: python -m backend.ml.train")
        return joblib.load(MODEL_PATH)

    @classmethod
    def exists(cls) -> bool:
        return MODEL_PATH.exists()

    # backward-compat alias used by train.py sanity check
    @property
    def auc(self) -> float:
        return 0.0


def _neutral_prediction(reason: str) -> dict:
    return {
        "direction": "FLAT", "probabilities": {}, "confidence": 0.0,
        "bull_prob": 0.0, "bear_prob": 0.0,
        "trade_side": None, "is_strong": False, "reason": reason,
    }
