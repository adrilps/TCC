"""
models/train.py — Treino de um modelo XGBoost por fase da partida.

Decisoes metodologicas implementadas aqui:
  1. Particao treino/teste POR JOGADOR (GroupShuffleSplit sobre o PUUID).
     Um mesmo jogador nunca aparece nos dois lados: sem isso o modelo pode
     memorizar o estilo do jogador em vez de aprender o efeito das metricas.
  2. Fases inexistentes sao excluidas, nao imputadas. Uma partida encerrada
     antes do Barao/25 min nao tem fase tardia; incluir a linha com zeros
     inventaria comportamento que nao ocorreu.
  3. NaN remanescente (ex.: proximidade de objetivo quando nenhum objetivo foi
     disputado na fase) e entregue ao XGBoost, que trata ausencia nativamente.
  4. Baseline de regressao logistica para contextualizar a AUC do XGBoost.
"""

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score

from lol_pipeline.config import PHASE_FEATURES, XGB_PARAMS, TEST_SIZE

AUC_MINIMO = 0.65  # limiar declarado na metodologia


def _fase_existe(df: pd.DataFrame, phase: str) -> pd.Series:
    col = f"{phase.lower()}_duration_min"
    return df[col] > 0 if col in df.columns else pd.Series(True, index=df.index)


def train_phase_models(df: pd.DataFrame, seed: int = None) -> dict:
    seed = seed if seed is not None else XGB_PARAMS["random_state"]
    models = {}

    for phase, features in PHASE_FEATURES.items():
        sub = df[_fase_existe(df, phase)].reset_index(drop=True)
        X, y = sub[features], sub["win"]
        groups = sub["puuid"] if "puuid" in sub.columns else pd.Series(np.arange(len(sub)))

        splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=seed)
        idx_train, idx_test = next(splitter.split(X, y, groups))
        X_train, X_test = X.iloc[idx_train], X.iloc[idx_test]
        y_train, y_test = y.iloc[idx_train], y.iloc[idx_test]

        model = xgb.XGBClassifier(**{**XGB_PARAMS, "random_state": seed})
        model.fit(X_train, y_train)
        auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])

        base = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(max_iter=1000))
        base.fit(X_train, y_train)
        auc_base = roc_auc_score(y_test, base.predict_proba(X_test)[:, 1])

        marca = "OK" if auc >= AUC_MINIMO else "ABAIXO DO LIMIAR"
        print(f"  {phase:<6} AUC = {auc:.3f}  (baseline LR {auc_base:.3f})  "
              f"[{marca}]  treino {len(X_train)} / teste {len(X_test)} "
              f"| jogadores {groups.iloc[idx_train].nunique()}/{groups.iloc[idx_test].nunique()}")

        models[phase] = {
            "model": model, "features": features,
            "X_train": X_train, "y_train": y_train,
            "X_test": X_test, "y_test": y_test,
            "auc": auc, "auc_baseline": auc_base,
            "n_treino": len(X_train), "n_teste": len(X_test),
            "jogadores_treino": int(groups.iloc[idx_train].nunique()),
            "jogadores_teste": int(groups.iloc[idx_test].nunique()),
        }

    return models


def avaliar_estabilidade(df: pd.DataFrame, seeds=(42, 7, 13, 99, 2024)) -> pd.DataFrame:
    """Repete a particao com varias sementes: mede se a AUC e estavel ou sorte."""
    linhas = []
    for s in seeds:
        for phase, obj in train_phase_models(df, seed=s).items():
            linhas.append({"semente": s, "fase": phase,
                           "auc": obj["auc"], "auc_baseline": obj["auc_baseline"]})
    return pd.DataFrame(linhas)


def tabela_metricas(models: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "fase": ph, "auc_xgboost": round(o["auc"], 4),
        "auc_baseline_lr": round(o["auc_baseline"], 4),
        "atinge_limiar_0_65": o["auc"] >= AUC_MINIMO,
        "n_treino": o["n_treino"], "n_teste": o["n_teste"],
        "jogadores_treino": o["jogadores_treino"], "jogadores_teste": o["jogadores_teste"],
    } for ph, o in models.items()])
