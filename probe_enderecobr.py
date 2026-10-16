"""Sonda: (1) confere o parquet gerado; (2) descobre a assinatura do
enderecobr embutido no geocodebr, para usar a padronização REAL em vez da
aproximação. Rode e cole a saída.

    python probe_enderecobr.py
"""

import inspect

import pandas as pd

from nereus_geocoding.config import OUT_DIR

# ---- (1) conferência do parquet de teste -----------------------------------
pq = OUT_DIR / "sp_2023.parquet"
print("=" * 70)
print(f"PARQUET: {pq}")
print("=" * 70)
if pq.exists():
    df = pd.read_parquet(pq)
    print("linhas:", len(df), "| colunas:", list(df.columns))
    print("\ndistribuição de precisao_best (tipo_resultado):")
    print(df["precisao_best"].value_counts(dropna=False).to_string())
    print("\ndistribuição de classe:")
    print(df["classe"].value_counts(dropna=False).to_string())
    print("\nmelhor variante escolhida (best_step):")
    print(df["best_step"].value_counts(dropna=False).to_string())
    print("\naceito:")
    print(df["aceito"].value_counts(dropna=False).to_string())
    print("\n5 linhas de amostra:")
    cols = ["id", "endereco", "best_step", "endereco_best", "precisao_best",
            "precisao_cat", "classe", "aceito", "lat", "lon"]
    print(df[[c for c in cols if c in df.columns]].head().to_string())
else:
    print("(parquet não encontrado)")

# ---- (2) enderecobr embutido no geocodebr -----------------------------------
import geocodebr

print()
print("=" * 70)
print("enderecobr via geocodebr")
print("=" * 70)
for nome in ("enderecobr_padronizar_enderecos", "standardize"):
    fn = getattr(geocodebr, nome, None)
    if fn is None:
        print(f"\n{nome}: NÃO existe")
        continue
    print(f"\n{nome} — assinatura:")
    try:
        print("   ", inspect.signature(fn))
    except (TypeError, ValueError) as e:
        print("    (sem assinatura:", e, ")")
    doc = (inspect.getdoc(fn) or "").strip()
    if doc:
        print("   doc:", doc[:800])

# Tenta rodar enderecobr_padronizar_enderecos num exemplo mínimo.
print("\n-- teste enderecobr_padronizar_enderecos:")
ex = pd.DataFrame({
    "logradouro": ["AV. PAULISTA", "R PROF JOSE NICOLI"],
    "numero": ["1578", "S/N"],
    "cep": ["01310100", "01310100"],
    "bairro": ["BELA VISTA", "CENTRO"],
    "municipio": ["3550308", "3550308"],
    "estado": ["SP", "SP"],
})
fn = getattr(geocodebr, "enderecobr_padronizar_enderecos", None)
if fn is not None:
    import polars as pl
    campos = {"logradouro": "logradouro", "numero": "numero", "cep": "cep",
              "localidade": "bairro", "municipio": "municipio", "estado": "estado"}
    try:
        out = fn(pl.from_pandas(ex), campos, formato_numeros="character")
        out_pd = out.to_pandas() if hasattr(out, "to_pandas") else pd.DataFrame(out)
        print("   OK -> colunas:", list(out_pd.columns))
        print(out_pd.to_string())
    except Exception as e:  # noqa: BLE001
        print("   falhou ->", repr(e)[:300])

# ---- (3) busca_por_cep: formato de saída -----------------------------------
print()
print("=" * 70)
print("busca_por_cep(cep=[...])")
print("=" * 70)
try:
    cep_res = geocodebr.busca_por_cep(cep=["01310100", "01310-100"])
    cep_pd = cep_res.to_pandas() if hasattr(cep_res, "to_pandas") else pd.DataFrame(cep_res)
    print("colunas:", list(cep_pd.columns))
    print(cep_pd.head(10).to_string())
except Exception as e:  # noqa: BLE001
    print("falhou:", repr(e)[:300])
