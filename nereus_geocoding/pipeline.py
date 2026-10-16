"""Pipeline end-to-end por região×ano: query -> tratamento -> geocoding -> parquet.

Espelha o papel de ``main_first_stage_geocoding`` do R, lendo a RAIS do DuckDB e
gravando um parquet por região×ano em ``OUT_DIR``. Retoma de onde parou: pula
região×ano cujo parquet já existe (a menos de ``overwrite``).
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path
from typing import Mapping, Optional, Sequence

import pandas as pd

from . import config, geocoding, quality, reader, recursos

# Metadados carregados da query e levados para a saída (1 linha por id).
_META_COLS = [
    "id", "identificad_m", "ano", "uf", "municipio", "municipio_7", "uf_dom",
    "cep", "bairro", "numlograd", "estoque", "matrizfilial", "clascnae20", "endereco",
]


def run_region_year(
    con,
    region: str,
    ufs: Sequence[str],
    year: int,
    out_dir: Path = config.OUT_DIR,
    cod_to_nome: Optional[Mapping] = None,
    sd_threshold_km: float = config.SD_THRESHOLD_KM,
    accept_single_point_cep: bool = config.ACCEPT_SINGLE_POINT_CEP,
    so_ativas: bool = config.SO_ATIVAS,
    limite: Optional[int] = None,
    overwrite: bool = False,
    verbose: bool = True,
) -> Optional[Path]:
    """Processa uma região×ano e grava o parquet. Devolve o caminho ou None."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{region}_{year}.parquet"

    if out_file.exists() and not overwrite:
        if verbose:
            print(f"[{region} {year}] já existe, pulando: {out_file.name}")
        return None

    t0 = time.time()
    df = reader.read_region_year(con, ufs, year, so_ativas=so_ativas)
    if limite is not None:
        df = df.head(limite)
    if df.empty:
        if verbose:
            print(f"[{region} {year}] sem linhas")
        return None

    # id precisa identificar a linha unicamente (dentro da região×ano).
    if df["id"].duplicated().any():
        n_dup = int(df["id"].duplicated().sum())
        warnings.warn(f"[{region} {year}] {n_dup} ids duplicados; mantendo o primeiro.")
        df = df.drop_duplicates("id", keep="first")

    df = reader.prepare_input(df)

    if verbose:
        print(f"[{region} {year}] {len(df):,} estabelecimentos — geocodificando 5 variantes...")

    geocoded = geocoding.geocode_pipeline(df, cod_to_nome=cod_to_nome, verboso=False)
    geocoded = quality.aplicar_aceite(
        geocoded, sd_threshold_km=sd_threshold_km,
        accept_single_point_cep=accept_single_point_cep,
    )

    meta = df[[c for c in _META_COLS if c in df.columns]].copy()
    out = meta.merge(geocoded, on="id", how="left")

    out.insert(0, "regiao", region)
    out.to_parquet(out_file, index=False)

    if verbose:
        dt = time.time() - t0
        n_ok = int((out["aceito"] == 1).sum())
        print(f"[{region} {year}] {len(out):,} linhas, {n_ok:,} aceitas em "
              f"{dt:.0f}s -> {out_file.name}{recursos.uso_proprio()}")
    return out_file


def run_all(
    regioes: Optional[Sequence[str]] = None,
    anos: Optional[Sequence[int]] = None,
    out_dir: Path = config.OUT_DIR,
    limite: Optional[int] = None,
    overwrite: bool = False,
    usar_nome_municipio: bool = False,
    verbose: bool = True,
):
    """Roda a pipeline para as regiões×anos pedidos (padrão: tudo em config)."""
    regioes = list(regioes) if regioes else list(config.REGIOES)
    anos = list(anos) if anos else list(config.ANOS)

    # Limites de recurso (prioridade baixa + teto rígido do Windows + medição).
    recursos.baixar_prioridade()
    recursos.aplicar_tetos_windows()
    recursos.iniciar_medicao()

    con = reader.connect(n_cores=config.N_CORES, memory_limit=recursos.memoria_duckdb())
    cod_to_nome = reader.municipios_cod_to_nome(con) if usar_nome_municipio else None

    import geocodebr
    config.GEOCODEBR_CACHE.mkdir(parents=True, exist_ok=True)
    geocodebr.definir_pasta_cache(str(config.GEOCODEBR_CACHE))

    feitos = []
    for region in regioes:
        ufs = config.REGIOES[region]
        for year in anos:
            try:
                path = run_region_year(
                    con, region, ufs, year, out_dir=out_dir,
                    cod_to_nome=cod_to_nome, limite=limite,
                    overwrite=overwrite, verbose=verbose,
                )
                if path is not None:
                    feitos.append(path)
            except Exception as e:  # noqa: BLE001
                warnings.warn(f"[{region} {year}] ERRO: {e}")
    con.close()
    return feitos
