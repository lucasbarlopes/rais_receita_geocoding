"""Padronização de campos da RAIS — port de ``R/data_standardization.R``.

Mantém o comportamento das funções R originais:

- :func:`ibge6_to_7`            <- ``ibge6_to_7``
- :func:`add_sigla_from_uf`     <- ``add_sigla_from_uf``
- :func:`change_cep_99999999_to_na` <- ``change_cep_99999999_to_na``
- :func:`add_col_if_missing`    <- ``add_col_if_missing``

Ao contrário do R (``data.table``, modificação por referência), as funções que
operam sobre um ``DataFrame`` modificam o objeto recebido in-place e também o
retornam, para permitir encadeamento.
"""

from __future__ import annotations

import re
from typing import Iterable

import numpy as np
import pandas as pd

__all__ = [
    "ibge6_to_7",
    "add_sigla_from_uf",
    "change_cep_99999999_to_na",
    "add_col_if_missing",
    "UF_MAP",
]

# Código numérico da UF (2 dígitos) -> sigla. Igual ao mapa do R.
UF_MAP = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}

_ONLY_DIGITS = re.compile(r"\D")


def _ibge6_to_7_scalar(cod6: str) -> str:
    """Dígito verificador de um único código IBGE de 6 dígitos.

    Replica o laço do R: posições pares (1-based) têm o dígito dobrado, e se
    passar de 9 subtrai-se 9; o DV é ``(10 - soma %% 10) %% 10``.
    """
    soma = 0
    for i, ch in enumerate(cod6, start=1):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        soma += d
    dv = (10 - soma % 10) % 10
    return cod6 + str(dv)


def ibge6_to_7(cod6: Iterable) -> pd.Series:
    """Converte códigos IBGE de 6 dígitos em 7 dígitos (com dígito verificador).

    Espelha ``ibge6_to_7`` do R: aceita valores ausentes (``NA``/``NaN``/None),
    que permanecem ausentes, e levanta erro se algum valor não-nulo não tiver
    exatamente seis dígitos.
    """
    s = pd.Series(list(cod6)) if not isinstance(cod6, pd.Series) else cod6.copy()

    # Representação em texto, preservando ausentes como NA.
    def _to_str(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return pd.NA
        # evita "123456.0" quando vem como float inteiro
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        return str(x)

    txt = s.map(_to_str)

    not_na = txt.notna()
    invalid = not_na & ~txt.fillna("").str.fullmatch(r"\d{6}")
    if invalid.any():
        raise ValueError("Municipality codes must have exactly six digits.")

    out = pd.Series([pd.NA] * len(txt), index=txt.index, dtype="object")
    idx = txt.index[not_na]
    out.loc[idx] = txt.loc[idx].map(_ibge6_to_7_scalar)
    return out


def add_sigla_from_uf(dt: pd.DataFrame, old_col: str, new_col: str) -> pd.DataFrame:
    """Cria ``new_col`` com a sigla da UF a partir do código numérico em ``old_col``.

    Espelha ``add_sigla_from_uf``: troca vírgula por ponto, converte para número,
    formata com dois dígitos (``%02d``) e mapeia pela tabela :data:`UF_MAP`.
    Códigos não reconhecidos viram ausentes.
    """
    if old_col not in dt.columns:
        raise KeyError(f"Column not found: {old_col}")

    x = dt[old_col].astype("string").str.strip().str.replace(",", ".", regex=False)
    num = pd.to_numeric(x, errors="coerce")
    code = num.map(lambda v: f"{int(v):02d}" if pd.notna(v) else pd.NA)
    dt[new_col] = code.map(lambda c: UF_MAP.get(c) if pd.notna(c) else pd.NA).astype("object")
    return dt


def change_cep_99999999_to_na(
    dt: pd.DataFrame, cep_column: str, municipio_column: str
) -> pd.DataFrame:
    """Troca o CEP sentinela ``99999999`` por ausente, exceto no município 412625.

    Espelha ``change_cep_99999999_to_na``.
    """
    for col in (cep_column, municipio_column):
        if col not in dt.columns:
            raise KeyError(f"Column not found: {col}")

    cep_str = dt[cep_column].astype("string")
    mun_str = dt[municipio_column].astype("string")
    mask = cep_str.notna() & (cep_str == "99999999") & (mun_str != "412625")
    if mask.any():
        dt.loc[mask, cep_column] = pd.NA
    return dt


def add_col_if_missing(dt: pd.DataFrame, col: str, value=pd.NA) -> pd.DataFrame:
    """Cria ``col`` com ``value`` se ela ainda não existir. Espelha ``add_col_if_missing``."""
    if col not in dt.columns:
        dt[col] = value
    return dt
