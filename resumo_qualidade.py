"""Resumo de qualidade dos parquets gerados (lê tudo em OUT_DIR via DuckDB).

    python resumo_qualidade.py

Mostra, por região×ano e no agregado: nº de linhas, % aceito, e a distribuição
por nível de precisão (número / logradouro / CEP / município).
"""

import duckdb

from nereus_geocoding.config import OUT_DIR

glob = (OUT_DIR / "*.parquet").as_posix()
con = duckdb.connect()

print("=" * 78)
print("POR REGIÃO × ANO")
print("=" * 78)
print(con.execute(f"""
    SELECT regiao, ano,
           count(*) AS linhas,
           sum(aceito) AS aceitas,
           round(100.0 * sum(aceito) / count(*), 1) AS pct_aceito,
           round(100.0 * count(*) FILTER (WHERE classe = 0) / count(*), 1) AS pct_classe0,
           round(100.0 * count(*) FILTER (WHERE classe = 1) / count(*), 1) AS pct_classe1,
           round(100.0 * count(*) FILTER (WHERE classe = 2) / count(*), 1) AS pct_classe2
    FROM read_parquet('{glob}')
    GROUP BY 1, 2 ORDER BY 1, 2
""").df().to_string(index=False))

print("\n" + "=" * 78)
print("DISTRIBUIÇÃO POR NÍVEL DE PRECISÃO (precisao_cat) — agregado")
print("=" * 78)
print(con.execute(f"""
    SELECT coalesce(precisao_cat, '(sem resultado)') AS nivel,
           count(*) AS n,
           round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
    FROM read_parquet('{glob}')
    GROUP BY 1 ORDER BY n DESC
""").df().to_string(index=False))

print("\n" + "=" * 78)
print("CÓDIGO DE PRECISÃO (tipo_resultado) — agregado, top 15")
print("=" * 78)
print(con.execute(f"""
    SELECT coalesce(precisao_best, '(sem resultado)') AS codigo,
           count(*) AS n,
           round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
    FROM read_parquet('{glob}')
    GROUP BY 1 ORDER BY n DESC LIMIT 15
""").df().to_string(index=False))

print("\n" + "=" * 78)
print("TOTAL GERAL")
print("=" * 78)
print(con.execute(f"""
    SELECT count(*) AS linhas,
           sum(aceito) AS aceitas,
           round(100.0 * sum(aceito) / count(*), 1) AS pct_aceito,
           count(DISTINCT identificad_m) AS estabelecimentos_distintos
    FROM read_parquet('{glob}')
""").df().to_string(index=False))
