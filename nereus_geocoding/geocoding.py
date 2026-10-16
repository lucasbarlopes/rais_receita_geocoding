"""Orquestração do geocoding — port de ``R/geocode_pipeline.R``.

Para cada estabelecimento, geocodifica 5 variantes do endereço e fica com a de
melhor precisão:

    raw    campos crus (endereco, numlograd, cep, bairro, municipio_7, uf_dom)
    pad    campos padronizados (aprox. enderecobr)
    lns_0  logradouro_num_string sobre o pad, modo no_cut
    lns_1  idem, modo cut_when_missing_num
    lns_2  idem, modo always_cut_on_stopword

Diferença em relação ao R: o geocodebr Python já devolve ``lat``/``lon`` e o
código de precisão em ``tipo_resultado``, então não há passo extra para
recuperar geometria.
"""

from __future__ import annotations

from typing import Mapping, Optional

import geocodebr
import pandas as pd

from . import address_cleaning, config, padronizacao, precision, recursos

# Ordem das variantes (empate de score é resolvido pela ÚLTIMA, como no R:
# max.col(..., ties.method = "last")).
STEP_ORDER = ["raw", "pad", "lns_0", "lns_1", "lns_2"]
_LNS_MODE = {
    "lns_0": "no_cut",
    "lns_1": "cut_when_missing_num",
    "lns_2": "always_cut_on_stopword",
}

# Mapeamento campo lógico -> coluna de entrada crua (etapa raw / base do pad).
_CAMPOS_RAW = {
    "logradouro": "endereco", "numero": "numlograd", "cep": "cep",
    "bairro": "bairro", "municipio": "municipio_7", "estado": "uf_dom",
}

_CAMPOS_GB = None


def _campos_gb():
    global _CAMPOS_GB
    if _CAMPOS_GB is None:
        _CAMPOS_GB = geocodebr.definir_campos(
            logradouro="logradouro", numero="numero", cep="cep",
            localidade="localidade", municipio="municipio", estado="estado",
        )
    return _CAMPOS_GB


def _to_pandas(res) -> pd.DataFrame:
    return res.to_pandas() if hasattr(res, "to_pandas") else pd.DataFrame(res)


def _fmt_num(x):
    """Número de logradouro como string inteira (ex.: 1578.0 -> '1578'); NA -> None."""
    if x is None or (isinstance(x, float) and pd.isna(x)) or (not isinstance(x, (int, float, str))):
        return None
    if isinstance(x, float):
        return str(int(x)) if x.is_integer() else str(x)
    if isinstance(x, str):
        return x.strip() or None
    return str(x)


def _variant_frame(id_s, logr, num, cep, loc, mun, est) -> pd.DataFrame:
    return pd.DataFrame({
        "id": id_s.values,
        "logradouro": logr.values,
        "numero": [_fmt_num(v) for v in num.tolist()],
        "cep": cep.values, "localidade": loc.values, "municipio": mun.values,
        "estado": est.values,
    })


def _padronizar(df_prep, cod_to_nome, usar_enderecobr_real, verboso):
    """Padroniza (etapa pad). Usa o enderecobr REAL (via geocodebr) e, se faltar
    algo, cai para a aproximação em Python."""
    if usar_enderecobr_real:
        try:
            return padronizacao.padronizar_enderecos_real(df_prep)
        except Exception as e:  # noqa: BLE001
            import warnings
            warnings.warn(
                f"enderecobr real indisponível ({e}); usando a aproximação Python."
            )
    return padronizacao.padronizar_enderecos(df_prep, _CAMPOS_RAW, cod_to_nome=cod_to_nome)


def _build_variants(df_prep: pd.DataFrame, cod_to_nome: Optional[Mapping] = None,
                    usar_enderecobr_real: bool = True, verboso: bool = False):
    """Monta os DataFrames das 5 variantes. Devolve (variants, dfp).

    ``df_prep`` precisa ter: id, endereco, numlograd, cep, bairro, municipio_7, uf_dom.
    """
    dfp = _padronizar(df_prep, cod_to_nome, usar_enderecobr_real, verboso)
    # numero_padr == "S/N" -> NA (igual ao R).
    dfp["numero_padr"] = dfp["numero_padr"].where(dfp["numero_padr"] != "S/N", other=pd.NA)

    variants = {}
    variants["raw"] = _variant_frame(
        df_prep["id"], df_prep["endereco"], df_prep["numlograd"], df_prep["cep"],
        df_prep["bairro"], df_prep["municipio_7"], df_prep["uf_dom"],
    )
    variants["pad"] = _variant_frame(
        dfp["id"], dfp["logradouro_padr"], dfp["numero_padr"], dfp["cep_padr"],
        dfp["bairro_padr"], dfp["municipio_padr"], dfp["estado_padr"],
    )
    for step, mode in _LNS_MODE.items():
        base = dfp[[
            "id", "logradouro_padr", "numero_padr", "cep_padr",
            "bairro_padr", "municipio_padr", "estado_padr",
        ]].copy()
        base = address_cleaning.logradouro_num_string(
            base, endereco_col="logradouro_padr", num_col="numero_padr",
            endereco_update_mode=mode,
        )
        variants[step] = _variant_frame(
            base["id"], base["endereco_limpo"], base["numlograd_novo"], base["cep_padr"],
            base["bairro_padr"], base["municipio_padr"], base["estado_padr"],
        )
    return variants, dfp


_KEY_COLS = ["logradouro", "numero", "cep", "localidade", "municipio", "estado"]


def _addr_key(df: pd.DataFrame) -> pd.Series:
    """Chave do endereço: os 6 campos concatenados (NA -> vazio)."""
    key = df[_KEY_COLS[0]].astype("string").fillna("")
    for c in _KEY_COLS[1:]:
        key = key.str.cat(df[c].astype("string").fillna(""), sep="|")
    return key


def _geocode_variant(
    vdf: pd.DataFrame, step: str, verboso: bool = False,
    dedup: bool = True, esperar: bool = True,
) -> pd.DataFrame:
    if esperar:
        recursos.esperar_folga()

    if dedup:
        # geocodifica cada endereço distinto uma vez só e remapeia por addr_key.
        work = vdf.copy()
        work["addr_key"] = _addr_key(work)
        uniq = work.drop_duplicates("addr_key")[["addr_key"] + _KEY_COLS]
        res = _to_pandas(geocodebr.geocode(
            enderecos=uniq, campos_endereco=_campos_gb(),
            resultado_completo=False, resolver_empates=True, verboso=verboso,
        ))
        res = res[["addr_key", "logradouro", "lat", "lon", "precisao",
                   "tipo_resultado", "desvio_metros", "endereco_encontrado"]]
        res = work[["id", "addr_key"]].merge(res, on="addr_key", how="left")
    else:
        res = _to_pandas(geocodebr.geocode(
            enderecos=vdf, campos_endereco=_campos_gb(),
            resultado_completo=False, resolver_empates=True, verboso=verboso,
        ))

    out = pd.DataFrame({
        "id": res["id"],
        "step": step,
        "step_order": STEP_ORDER.index(step),
        "precisao_best": res["tipo_resultado"],
        "precisao_cat": res.get("precisao"),
        "lat": res["lat"],
        "lon": res["lon"],
        "desvio_metros": res.get("desvio_metros"),
        "endereco_encontrado": res.get("endereco_encontrado"),
        "endereco_best": res["logradouro"],
    })
    out["best_score"] = precision.score_from_codes(out["precisao_best"])
    return out


def geocode_pipeline(
    df_prep: pd.DataFrame,
    cod_to_nome: Optional[Mapping] = None,
    verboso: bool = False,
    usar_enderecobr_real: bool = True,
    dedup: Optional[bool] = None,
) -> pd.DataFrame:
    """Geocodifica as 5 variantes e devolve 1 linha por ``id`` com a melhor.

    Colunas devolvidas: id, best_step, endereco_best, endereco_fonte,
    precisao_best, best_score, precisao_cat, lat, lon, desvio_metros,
    endereco_encontrado, cep_padr.
    """
    if dedup is None:
        dedup = config.DEDUP_ENDERECOS

    variants, dfp = _build_variants(
        df_prep, cod_to_nome=cod_to_nome,
        usar_enderecobr_real=usar_enderecobr_real, verboso=verboso,
    )

    # Espera a máquina ter folga uma vez por região×ano (antes das 5 variantes).
    recursos.esperar_folga()
    partes = [
        _geocode_variant(variants[s], s, verboso=verboso, dedup=dedup, esperar=False)
        for s in STEP_ORDER
    ]
    allv = pd.concat(partes, ignore_index=True)

    # Melhor por id: menor score; empate -> maior step_order (última variante).
    allv = allv.sort_values(
        ["id", "best_score", "step_order"],
        ascending=[True, True, False], na_position="last",
    )
    best = allv.drop_duplicates("id", keep="first").copy()

    # best_step/precisao_best = NA quando nenhuma variante teve score.
    sem_score = best["best_score"].isna()
    best.loc[sem_score, "step"] = pd.NA
    best.loc[sem_score, "precisao_best"] = pd.NA

    best["endereco_fonte"] = best["step"]
    best = best.rename(columns={"step": "best_step"})

    # Anexa cep_padr (usado no filtro de consistência de CEP).
    cep_padr = dfp[["id", "cep_padr"]].drop_duplicates("id")
    best = best.merge(cep_padr, on="id", how="left")

    cols = [
        "id", "best_step", "endereco_best", "endereco_fonte", "precisao_best",
        "best_score", "precisao_cat", "lat", "lon", "desvio_metros",
        "endereco_encontrado", "cep_padr",
    ]
    return best[cols].reset_index(drop=True)
