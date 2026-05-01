"""
Volatility Regime Classifier — RandomForest multi-class.

Trained on NIFTY + BANKNIFTY 5-minute candles.
Regimes: LOW_VOL | MED_VOL | HIGH_VOL | SPIKE | TRENDING_UP | TRENDING_DOWN | RANGING

Buy-side strategy per regime:
  LOW_VOL      → Cheapest premium → best time to buy options aggressively
  MED_VOL      → Fair premium → buy selectively with good direction signal
  TRENDING_UP  → Buy CE with momentum, premium rising fast
  TRENDING_DOWN→ Buy PE with momentum, premium rising fast
  RANGING      → Avoid naked buys — market will likely pin near max pain
  HIGH_VOL     → Premium expensive → reduce size or skip
  SPIKE        → Extreme fear/greed → options too expensive, avoid buying
"""

from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report
from sklearn.preprocessing import LabelEncoder

from backend.ml.features import (
    compute_features, label_regime,
    REGIME_MODEL_FEATURES, REGIME_CLASSES, MIN_ROWS,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_PATH   = Path(__file__).parent / "models" / "regime_model.pkl"

# Per-regime: (strategy, should_buy_options, size_multiplier)
REGIME_META = {
    "LOW_VOL":       ("buy_aggressively",   True,  1.2),
    "MED_VOL":       ("buy_selectively",    True,  1.0),
    "TRENDING_UP":   ("buy_CE_momentum",    True,  1.1),
    "TRENDING_DOWN": ("buy_PE_momentum",    True,  1.1),
    "RANGING":       ("avoid",              False, 0.0),
    "HIGH_VOL":      ("reduce_size",        True,  0.6),
    "SPIKE":         ("avoid",              False, 0.0),
}


def build_training_data(
    fivemin_data: dict[str, pd.DataFrame],
    sample_every: int = 3,
) -> tuple[pd.DataFrame, pd.Series]:
    frames = []
    for symbol, df in fivemin_data.items():
        if len(df) < MIN_ROWS:
            continue
        df_feat = compute_features(df)
        df_feat["label_regime"] = label_regime(df_feat)
        df_feat = df_feat.dropna(subset=REGIME_MODEL_FEATURES + ["label_regime"])
        if len(df_feat) < MIN_ROWS:
            continue
        frames.append(df_feat.iloc[::sample_every][REGIME_MODEL_FEATURES + ["label_regime", "date"]])

    if not frames:
        raise ValueError("No usable 5-minute data for regime model")

    combined = pd.concat(frames, ignore_index=True).sort_values("date")
    X = combined[REGIME_MODEL_FEATURES].astype(float)
    y = combined["label_regime"]

    dist = y.value_counts(normalize=True)
    logger.info(f"Regime training set: {len(X):,} rows\n{dist.to_string()}")
    return X, y


def train(fivemin_data: dict[str, pd.DataFrame]) -> "RegimeModel":
    X, y = build_training_data(fivemin_data)

    le = LabelEncoder()
    le.fit(REGIME_CLASSES)
    y_enc = le.transform(y)

    rf = RandomForestClassifier(
        n_estimators=400,
        max_depth=14,
        min_samples_leaf=30,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )

    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, val_idx = splits[-1]

    logger.info(f"Training RandomForest on {len(train_idx):,} rows…")
    rf.fit(X.iloc[train_idx], y_enc[train_idx])

    y_pred = rf.predict(X.iloc[val_idx])
    logger.info("\nRegime Model Validation:")
    logger.info("\n" + classification_report(
        y_enc[val_idx], y_pred, target_names=le.classes_
    ))

    fi = pd.Series(rf.feature_importances_, index=REGIME_MODEL_FEATURES)
    logger.info(f"\nTop features:\n{fi.sort_values(ascending=False).head(8).to_string()}")

    model = RegimeModel(rf, le)
    model.save()
    return model


class RegimeModel:
    def __init__(self, clf: RandomForestClassifier, encoder: LabelEncoder):
        self.clf     = clf
        self.encoder = encoder

    def predict(self, df: pd.DataFrame) -> dict:
        """
        Classify current market regime from 5-min OHLCV candles.
        Returns {regime, strategy, should_buy_options, size_multiplier, confidence}.
        """
        if len(df) < MIN_ROWS:
            return _default_regime("insufficient_data")

        df_feat = compute_features(df)
        row = df_feat[REGIME_MODEL_FEATURES].dropna().tail(1)
        if row.empty:
            return _default_regime("nan_features")

        probs    = self.clf.predict_proba(row)[0]
        pred_idx = int(np.argmax(probs))
        regime   = self.encoder.inverse_transform([pred_idx])[0]

        prob_dict = {
            cls: round(float(p), 3)
            for cls, p in zip(self.encoder.classes_, probs)
        }

        strategy, should_buy, size_mult = REGIME_META.get(regime, ("selective", True, 1.0))

        return {
            "regime":             regime,
            "probabilities":      prob_dict,
            "confidence":         round(float(max(probs)), 3),
            "strategy":           strategy,
            "should_buy_options": should_buy,
            "size_multiplier":    size_mult,
        }

    def predict_batch(self, df: pd.DataFrame) -> pd.Series:
        """Classify every row in df (backtesting)."""
        df_feat = compute_features(df)
        valid   = df_feat[REGIME_MODEL_FEATURES].dropna()
        if valid.empty:
            return pd.Series("MED_VOL", index=df.index, dtype=str)
        preds  = self.encoder.inverse_transform(self.clf.predict(valid))
        result = pd.Series("MED_VOL", index=df.index, dtype=str)
        result.loc[valid.index] = preds
        return result

    def save(self):
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, MODEL_PATH)
        logger.info(f"Regime model saved → {MODEL_PATH}")

    @classmethod
    def load(cls) -> "RegimeModel":
        if not MODEL_PATH.exists():
            raise FileNotFoundError("Regime model not found. Run: python -m backend.ml.train")
        return joblib.load(MODEL_PATH)

    @classmethod
    def exists(cls) -> bool:
        return MODEL_PATH.exists()


def _default_regime(reason: str) -> dict:
    return {
        "regime": "MED_VOL", "probabilities": {}, "confidence": 0.0,
        "strategy": "buy_selectively", "should_buy_options": True,
        "size_multiplier": 0.5, "reason": reason,
    }
