"""Pontuação e classificação de precisão — port de ``R/precision.R``.

O geocodebr devolve o código de precisão na coluna ``tipo_resultado`` (ex.:
``da01``, ``dc02``, ``dm01``). :data:`PRECISION_ORDER` lista os códigos do melhor
para o pior; o score é a posição (1 = melhor).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["PRECISION_ORDER", "score_from_codes", "classificar_precisao"]

PRECISION_ORDER = [
    "dn01", "dn02", "dn03", "dn04",
    "pn01", "pn02", "pn03", "pn04",
    "da01", "da02", "da03", "da04",
    "pa01", "pa02", "pa03", "pa04",
    "dl01", "dl02", "dl03", "dl04",
    "pl01", "pl02", "pl03", "pl04",
    "dc01", "dc02", "db01", "dm01",
]
_SCORE = {code: i + 1 for i, code in enumerate(PRECISION_ORDER)}


def score_from_codes(codes: pd.Series) -> pd.Series:
    """Mapeia códigos de ``tipo_resultado`` para score numérico (1 = melhor).

    Código ausente ou não mapeado -> ``NaN`` (espelha ``criar_score_precisao``).
    """
    out = codes.map(lambda c: _SCORE.get(c, np.nan) if pd.notna(c) else np.nan)
    unmapped = codes.notna() & out.isna()
    if unmapped.any():
        vals = sorted(set(codes[unmapped].dropna()))
        import warnings
        warnings.warn(f"Precisões não mapeadas para score: {vals}")
    return out.astype("float64")


def classificar_precisao(precisao_best: pd.Series) -> pd.Series:
    """Classe de precisão (port de ``classificar_precisao_best``).

    - ``NA`` -> NA
    - ``db01``/``dm01`` -> 2 (baixa; rejeitada)
    - ``dc01``/``dc02`` -> 1 (nível CEP; depende do filtro de consistência)
    - caso contrário -> 0 (boa; aceita direto)
    """
    def _one(p):
        if p is None or (isinstance(p, float) and pd.isna(p)) or pd.isna(p):
            return pd.NA
        if p in ("db01", "dm01"):
            return 2
        if p in ("dc01", "dc02"):
            return 1
        return 0

    return precisao_best.map(_one).astype("Int64")
