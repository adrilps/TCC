"""
models/train.py — Per-phase XGBoost model training.
"""

import xgboost as xgb
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

from lol_pipeline.config import PHASE_FEATURES, XGB_PARAMS, TEST_SIZE


def train_phase_models(df: pd.DataFrame) -> dict:
    """
    Trains one XGBoost classifier per game phase.
    Each model sees only its phase's features — this is intentional.
    Mixing all features into one model would conflate phase-specific signal.

    Returns a dict: { phase_name: { model, features, X_test, y_test } }
    """
    models = {}
    for phase, features in PHASE_FEATURES.items():
        X = df[features]
        y = df["win"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=XGB_PARAMS["random_state"]
        )

        model = xgb.XGBClassifier(**XGB_PARAMS)
        model.fit(X_train, y_train)

        auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
        print(f"  {phase}: AUC = {auc:.3f}")

        models[phase] = {
            "model": model,
            "features": features,
            "X_test": X_test,
            "y_test": y_test,
        }

    return models
