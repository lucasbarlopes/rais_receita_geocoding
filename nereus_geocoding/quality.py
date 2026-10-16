"""Filtro de consistência de CEP e aceite — port de ``R/quality_filters.R``.

Classe 1 (precisão de CEP: ``dc01``/``dc02``) só é aceita se o CEP for
consistente: busca os pontos do CEP via ``geocodebr.busca_por_cep`` e mede a
dispersão; aceita se houver um único ponto (quando ``accept_single_point_cep``)
ou se o desvio-padrão das distâncias ao centroide for <= ``sd_threshold_km``.

Diferença em relação ao R: a dispersão é calculada com distância de haversine
(em vez de projeção para um CRS métrico). A diferença numérica é desprezível na
escala de um CEP.
"""

from __future__ import annotations

import math
import warnings
from typing import Iterable, Set

import numpy as np
import pandas as pd

__all__ = ["filtrar_ceps_consistentes", "aplicar_aceite"]

_EARTH_M = 6_371_000.0


def _to_pandas(res) -> pd.DataFrame:
    return res.to_pandas() if hasattr(res, "to_pandas") else pd.DataFrame(res)


def _find_col(cols, *keywords):
    low = {c.lower(): c for c in cols}
    for kw in keywords:
        for lc, orig in low.items():
            if kw in lc:
                return orig
    return None


def _haversine_m(lat, lon, lat0, lon0):
    lat = np.radians(lat); lon = np.radians(lon)
    lat0 = math.radians(lat0); lon0 = math.radians(lon0)
    dlat = lat - lat0; dlon = lon - lon0
    a = np.sin(dlat / 2) ** 2 + np.cos(lat) * math.cos(lat0) * np.sin(dlon / 2) ** 2
    return 2 * _EARTH_M * np.arcsin(np.sqrt(a))


def filtrar_ceps_consistentes(
    ceps: Iterable[str],
    sd_threshold_km: float = 0.3,
    accept_single_point_cep: bool = True,
) -> Set[str]:
    """Retorna o conjunto de CEPs aceitos pelo critério de dispersão.

    Em caso de falha na busca (ex.: API indisponível), avisa e devolve conjunto
    vazio — classe 1 fica rejeitada, como faria o R sem pontos.
    """
    import geocodebr

    ceps = sorted({c for c in ceps if isinstance(c, str) and c})
    if not ceps:
        return set()

    try:
        res = _to_pandas(geocodebr.busca_por_cep(cep=ceps))
    except Exception as e:  # noqa: BLE001
        warnings.warn(f"busca_por_cep falhou ({e}); nenhum CEP classe-1 será aceito.")
        return set()

    if res.empty:
        return set()

    cep_col = _find_col(res.columns, "cep")
    lat_col = _find_col(res.columns, "lat")
    lon_col = _find_col(res.columns, "lon", "lng")
    if not (cep_col and lat_col and lon_col):
        warnings.warn(
            f"busca_por_cep devolveu colunas inesperadas ({list(res.columns)}); "
            "não foi possível avaliar consistência de CEP."
        )
        return set()

    df = res[[cep_col, lat_col, lon_col]].rename(
        columns={cep_col: "cep", lat_col: "lat", lon_col: "lon"}
    )
    df = df.dropna(subset=["lat", "lon"])
    df["cep"] = df["cep"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(8)

    aceitos: Set[str] = set()
    for cep, g in df.groupby("cep"):
        n = len(g)
        if n < 2:
            if accept_single_point_cep and n == 1:
                aceitos.add(cep)
            continue
        lat0 = g["lat"].mean()
        lon0 = g["lon"].mean()
        d = _haversine_m(g["lat"].to_numpy(), g["lon"].to_numpy(), lat0, lon0)
        sd_km = float(np.std(d, ddof=1)) / 1000.0
        if not np.isnan(sd_km) and sd_km <= sd_threshold_km:
            aceitos.add(cep)
    return aceitos


def aplicar_aceite(
    df: pd.DataFrame,
    sd_threshold_km: float = 0.3,
    accept_single_point_cep: bool = True,
    classe_col: str = "classe",
    cep_col: str = "cep_padr",
    aceito_col: str = "aceito",
) -> pd.DataFrame:
    """Adiciona ``classe`` (se ausente) e ``aceito`` ao DataFrame geocodificado.

    Regra (port de ``filtrar_enderecos_aceitos``):
    classe 0 -> aceito; classe 1 -> aceito só se o CEP for consistente; senão 0.
    """
    from . import precision

    if classe_col not in df.columns:
        df[classe_col] = precision.classificar_precisao(df["precisao_best"])

    # Normaliza o CEP para 8 dígitos: o enderecobr devolve "xxxxx-xxx" (com
    # hífen) e os CEPs aceitos são comparados sem pontuação.
    cep_norm = (
        df[cep_col].astype("string")
        .str.replace(r"\D", "", regex=True)
        .str.zfill(8)
        .where(lambda s: s.str.fullmatch(r"\d{8}"), other=pd.NA)
    )

    ceps_classe1 = cep_norm[df[classe_col] == 1].dropna().unique()
    aceitos = filtrar_ceps_consistentes(
        ceps_classe1, sd_threshold_km=sd_threshold_km,
        accept_single_point_cep=accept_single_point_cep,
    )

    # Condições como booleanos numpy puros: classe é Int64 (nullable) e fica <NA>
    # quando o endereço não geocodificou; passar <NA> direto ao np.where estoura
    # ("boolean value of NA is ambiguous"). NA -> False (não aceito).
    classe = df[classe_col]
    is_classe0 = (classe == 0).fillna(False).to_numpy(dtype=bool)
    is_classe1 = (classe == 1).fillna(False).to_numpy(dtype=bool)
    cep_ok = pd.Series(cep_norm.isin(aceitos), index=df.index).fillna(False).to_numpy(dtype=bool)

    aceito = np.where(is_classe0, 1, np.where(is_classe1 & cep_ok, 1, 0))
    # onde classe é NA ambos is_classe* são False, então aceito já é 0.
    df[aceito_col] = pd.Series(aceito, index=df.index).astype("Int64")
    return df
