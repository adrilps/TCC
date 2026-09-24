"""
explainability/shap_analysis.py — Importancia empirica via TreeSHAP.

A media dos valores absolutos de SHAP no conjunto de teste e a importancia
empirica de cada metrica: e ela que substitui os pesos arbitrarios usados por
ferramentas comerciais no metodo de comparacao individual.
"""

import numpy as np
import pandas as pd
import shap

# Rotulos em portugues para as figuras e tabelas do texto
ROTULOS = {
    "cs_per_min": "Farm (CS/min)",
    "vision_per_min": "Visão (wards/min)",
    "deaths_per_min": "Mortes/min",
    "dano_por_min": "Dano a campeões/min",
    "trocas_por_min": "Participação em trocas/min",
    "presenca_lutas_por_min": "Presença em combates/min",
    "participacoes_por_min": "Participação em abates/min",
    "kill_participation": "Participação em abates (razão)",
    "damage_share": "Parcela de dano da equipe",
    "solo_kills": "Abates solo",
    "objective_proximity": "Proximidade de objetivos",
    "first_blood_involved": "Envolvimento no first blood",
}


def rotulo(feature: str) -> str:
    for sufixo, nome in ROTULOS.items():
        if feature.endswith(sufixo):
            return nome
    return feature


def compute_shap(models: dict) -> dict:
    shap_results = {}
    for phase, obj in models.items():
        explainer = shap.TreeExplainer(obj["model"])
        shap_values = explainer.shap_values(obj["X_test"])
        importance = pd.Series(np.abs(shap_values).mean(axis=0),
                               index=obj["features"]).sort_values(ascending=False)
        shap_results[phase] = {
            "shap_values": shap_values,
            "importance": importance,
            "importance_norm": importance / importance.sum(),
            "X_test": obj["X_test"],
            "auc": obj.get("auc"),
        }
    return shap_results


def tabela_importancias(shap_results: dict) -> pd.DataFrame:
    linhas = []
    for phase, res in shap_results.items():
        for feat, val in res["importance_norm"].items():
            linhas.append({"fase": phase, "metrica": feat,
                           "rotulo": rotulo(feat),
                           "importancia_normalizada": round(float(val), 4)})
    return pd.DataFrame(linhas)


def print_importances(shap_results: dict):
    for phase, res in shap_results.items():
        print(f"  {phase}  (AUC {res['auc']:.3f})" if res.get("auc") else f"  {phase}")
        for feat, val in res["importance_norm"].items():
            print(f"    {rotulo(feat):<30} {val:.3f}")
        print()
