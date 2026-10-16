"""Gera um Excel com o resumo da precisão do geocoding por UF × ano.

Lê todos os parquets em OUT_DIR (via DuckDB, sem carregar tudo em memória) e
grava ``resumo_precisao_uf_ano.xlsx`` na MESMA pasta dos parquets, com abas:

    uf_ano            uma linha por UF×ano: nº de linhas, aceitas, % aceito e a
                      distribuição por classe de precisão (0/1/2/sem resultado).
    pct_aceito        matriz UF (linhas) × ano (colunas) com o % aceito.
    precisao_cat_pct  % de cada categoria de precisão (precisao_cat) por UF×ano.
    legenda           o que significa cada classe/categoria.

Uso:
    python resumo_excel.py
    python resumo_excel.py --out "D:\\outro\\caminho\\resumo.xlsx"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

from nereus_geocoding.config import OUT_DIR

LEGENDA = [
    ("aceito", "1 = endereço aceito (classe 0, ou classe 1 com CEP consistente); 0 = rejeitado."),
    ("classe 0", "Precisão boa (número/logradouro): aceita direto."),
    ("classe 1", "Precisão de CEP (dc01/dc02): aceita só se o CEP for consistente."),
    ("classe 2", "Precisão baixa (bairro/município, db01/dm01): rejeitada."),
    ("sem resultado", "Nenhuma das 5 variantes geocodificou o endereço (classe nula)."),
    ("precisao_cat", "Categoria de precisão devolvida pelo geocodebr (número, logradouro, CEP, localidade, município)."),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="caminho do .xlsx (padrão: OUT_DIR/resumo_precisao_uf_ano.xlsx)")
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else OUT_DIR / "resumo_precisao_uf_ano.xlsx"
    glob = (OUT_DIR / "*.parquet").as_posix()
    con = duckdb.connect()

    # --- Resumo principal: UF × ano -----------------------------------------
    uf_ano = con.execute(f"""
        SELECT uf, ano,
               count(*)                                      AS linhas,
               sum(aceito)                                   AS aceitas,
               round(100.0 * sum(aceito) / count(*), 1)      AS pct_aceito,
               count(*) FILTER (WHERE classe = 0)            AS n_classe0,
               count(*) FILTER (WHERE classe = 1)            AS n_classe1,
               count(*) FILTER (WHERE classe = 2)            AS n_classe2,
               count(*) FILTER (WHERE classe IS NULL)        AS n_sem_resultado,
               round(100.0 * count(*) FILTER (WHERE classe = 0)       / count(*), 1) AS pct_classe0,
               round(100.0 * count(*) FILTER (WHERE classe = 1)       / count(*), 1) AS pct_classe1,
               round(100.0 * count(*) FILTER (WHERE classe = 2)       / count(*), 1) AS pct_classe2,
               round(100.0 * count(*) FILTER (WHERE classe IS NULL)   / count(*), 1) AS pct_sem_resultado
        FROM read_parquet('{glob}')
        GROUP BY uf, ano
        ORDER BY uf, ano
    """).df()

    # --- Pivot UF × ano com o % aceito --------------------------------------
    pct_aceito = uf_ano.pivot(index="uf", columns="ano", values="pct_aceito")

    # --- Distribuição por categoria de precisão (precisao_cat), em % --------
    cat = con.execute(f"""
        SELECT uf, ano,
               coalesce(CAST(precisao_cat AS VARCHAR), '(sem resultado)') AS categoria,
               count(*) AS n
        FROM read_parquet('{glob}')
        GROUP BY 1, 2, 3
    """).df()
    cat_tot = cat.groupby(["uf", "ano"])["n"].transform("sum")
    cat["pct"] = (100.0 * cat["n"] / cat_tot).round(1)
    precisao_cat_pct = (
        cat.pivot_table(index=["uf", "ano"], columns="categoria", values="pct",
                        fill_value=0.0)
        .reset_index()
    )

    legenda = pd.DataFrame(LEGENDA, columns=["termo", "significado"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        uf_ano.to_excel(xw, sheet_name="uf_ano", index=False)
        pct_aceito.to_excel(xw, sheet_name="pct_aceito")
        precisao_cat_pct.to_excel(xw, sheet_name="precisao_cat_pct", index=False)
        legenda.to_excel(xw, sheet_name="legenda", index=False)

    print(f"OK: {len(uf_ano)} linhas (UF×ano) -> {out_path}")


if __name__ == "__main__":
    main()
