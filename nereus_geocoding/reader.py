"""Leitura da RAIS direto do DuckDB — substitui o ``data.table::fread`` de CSVs.

Fornece:
- :func:`connect`               abre a conexão e dá ATTACH no banco da RAIS;
- :func:`read_region_year`      SELECT de uma região (lista de UFs) × ano;
- :func:`prepare_input`         padroniza os campos (municipio_7, uf_dom, CEP);
- :func:`municipios_cod_to_nome` tabela código IBGE (7) -> nome, de rais.municipios.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

import duckdb
import pandas as pd

from . import standardization
from .config import DB_RAIS

# Colunas lidas de rais.estabelecimentos (nomes reais do banco).
_COLS_EST = [
    "id", "identificad_m", "endereco", "numlograd", "cep", "bairro",
    "municipio", "uf", "estoque", "matrizfilial", "clascnae20", "ano",
]


def connect(db_path: str = DB_RAIS, n_cores: Optional[int] = None,
            memory_limit: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    """Abre uma conexão DuckDB e dá ATTACH no banco da RAIS em modo leitura."""
    con = duckdb.connect()
    if n_cores:
        con.execute(f"SET threads = {int(n_cores)}")
    if memory_limit:
        con.execute(f"SET memory_limit = '{memory_limit}'")
    con.execute(f"ATTACH '{db_path}' AS rais (READ_ONLY)")
    return con


def read_region_year(
    con: duckdb.DuckDBPyConnection,
    ufs: Iterable[str],
    year: int,
    so_ativas: bool = False,
) -> pd.DataFrame:
    """Lê os estabelecimentos de um conjunto de UFs (uma região) num ano.

    Devolve um ``DataFrame`` com as colunas de :data:`_COLS_EST`.
    """
    uf_list = ", ".join(f"'{u}'" for u in ufs)
    filtros = [f"ano = {int(year)}", f"uf IN ({uf_list})"]
    if so_ativas:
        # indativano: '1' = ativo no ano (ajuste se o código do seu banco diferir).
        filtros.append("indativano = '1'")
    sql = f"""
        SELECT {', '.join(_COLS_EST)}
        FROM rais.estabelecimentos
        WHERE {' AND '.join(filtros)}
    """
    return con.execute(sql).df()


def municipios_cod_to_nome(con: duckdb.DuckDBPyConnection) -> Dict[str, str]:
    """Retorna {codigo_ibge (7 dígitos): nome} a partir de rais.municipios."""
    df = con.execute("SELECT codigo_ibge, nome FROM rais.municipios").df()
    return dict(zip(df["codigo_ibge"].astype(str), df["nome"].astype(str)))


def prepare_input(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os campos lidos, espelhando ``standardize_first_stage_input`` do R.

    - ``municipio_7``: código IBGE de 6 dígitos -> 7 (inválido -> NA);
    - ``uf_dom``: a coluna ``uf`` já é sigla no banco, copiada direto;
    - CEP sentinela ``99999999`` -> NA (exceto município 412625);
    - garante ``bairro`` e ``numlograd``.

    Modifica e devolve o DataFrame recebido.
    """
    standardization.add_col_if_missing(df, "bairro", pd.NA)
    standardization.add_col_if_missing(df, "numlograd", pd.NA)

    # municipio (6 dígitos) -> municipio_7, tolerante a valores inválidos.
    mun = df["municipio"].astype("string").str.replace(r"\.0$", "", regex=True)
    valid = mun.str.fullmatch(r"\d{6}").fillna(False)
    df["municipio_7"] = pd.Series(pd.NA, index=df.index, dtype="object")
    if valid.any():
        df.loc[valid, "municipio_7"] = standardization.ibge6_to_7(mun[valid]).values

    # uf já é sigla no banco.
    df["uf_dom"] = df["uf"].astype("string").str.upper().str.strip()

    standardization.change_cep_99999999_to_na(df, "cep", "municipio")
    return df
