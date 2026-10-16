"""Inspeciona o schema do banco DuckDB da RAIS para montar a camada de query.

Rodar:  python inspecionar_rais.py
Requer: duckdb  (pip install duckdb)

Não faz varredura pesada: só DESCRIBE + algumas linhas de amostra.
Cole a saída inteira de volta no chat.
"""

import duckdb

DB_RAIS = r"D:\Bases\MTE\RAIS_MTE_BRASIL\rais\db\rais_brasil.duckdb"

con = duckdb.connect()
con.execute(f"ATTACH '{DB_RAIS}' AS rais (READ_ONLY)")

print("=" * 70)
print("TABELAS em rais")
print("=" * 70)
print(con.execute("SHOW TABLES FROM rais").df().to_string(index=False))

for tabela in ("rais.estabelecimentos", "rais.municipios"):
    print()
    print("=" * 70)
    print(f"DESCRIBE {tabela}")
    print("=" * 70)
    try:
        cols = con.execute(f"DESCRIBE {tabela}").df()
        print(cols[["column_name", "column_type"]].to_string(index=False))
    except Exception as e:
        print(f"(erro: {e})")
        continue

    print(f"\n-- 3 linhas de amostra de {tabela}:")
    try:
        print(con.execute(f"SELECT * FROM {tabela} LIMIT 3").df().to_string())
    except Exception as e:
        print(f"(erro na amostra: {e})")

# Tenta identificar a coluna de ano/competência e de UF e seus valores distintos.
print()
print("=" * 70)
print("VALORES DISTINTOS de prováveis colunas de ano e UF em estabelecimentos")
print("=" * 70)
cols_est = [r[0] for r in con.execute("DESCRIBE rais.estabelecimentos").fetchall()]
low = {c.lower(): c for c in cols_est}
for alvo in ("ano", "competencia", "uf", "sg_uf", "sigla_uf", "cduf"):
    if alvo in low:
        real = low[alvo]
        try:
            vals = con.execute(
                f"SELECT DISTINCT {real} AS v FROM rais.estabelecimentos ORDER BY v"
            ).df()
            print(f"\n{real}: {vals['v'].tolist()}")
        except Exception as e:
            print(f"\n{real}: (erro: {e})")
