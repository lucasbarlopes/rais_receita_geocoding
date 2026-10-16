"""Sonda a API do geocodebr Python: colunas e valores de precisão do geocode(),
e se busca_por_cep existe. Rode e cole a saída inteira.

    python probe_geocodebr.py

Requer: geocodebr, pandas  (pip install geocodebr pandas)
"""

import geocodebr
import pandas as pd

from nereus_geocoding.config import GEOCODEBR_CACHE

print("geocodebr versão:", getattr(geocodebr, "__version__", "??"))
print("atributos do módulo:", [a for a in dir(geocodebr) if not a.startswith("_")])

GEOCODEBR_CACHE.mkdir(parents=True, exist_ok=True)
try:
    geocodebr.definir_pasta_cache(str(GEOCODEBR_CACHE))
except Exception as e:
    print("definir_pasta_cache falhou:", e)

# Amostra pequena, com endereços de precisões variadas.
df = pd.DataFrame({
    "id": ["1", "2", "3", "4"],
    "logradouro": ["AVENIDA PAULISTA", "RUA BARAO DE ITAPETININGA", "RUA INEXISTENTE XPTO", None],
    "numero": ["1578", "100", None, None],
    "cep": ["01310100", "01042000", None, "01001000"],
    "localidade": ["BELA VISTA", "REPUBLICA", None, None],
    "municipio": ["3550308", "3550308", "3550308", "3550308"],
    "estado": ["SP", "SP", "SP", "SP"],
})

campos = geocodebr.definir_campos(
    logradouro="logradouro", numero="numero", cep="cep",
    localidade="localidade", municipio="municipio", estado="estado",
)

print("\n=== geocode(resultado_completo=False) ===")
res = geocodebr.geocode(
    enderecos=df, campos_endereco=campos,
    resultado_completo=False, resolver_empates=True, verboso=False,
)
# res pode ser pyarrow.Table — converte para pandas para inspeção.
res_pd = res.to_pandas() if hasattr(res, "to_pandas") else pd.DataFrame(res)
print("colunas:", list(res_pd.columns))
print(res_pd.to_string())

# Quais colunas parecem de precisão e seus valores distintos.
for col in res_pd.columns:
    if any(k in col.lower() for k in ("precis", "tipo_result", "result")):
        print(f"\nvalores distintos de {col!r}:", res_pd[col].dropna().unique().tolist())

print("\n=== busca_por_cep ? ===")
if hasattr(geocodebr, "busca_por_cep"):
    try:
        cep_res = geocodebr.busca_por_cep(ceps=["01310100", "01042000"])
        cep_pd = cep_res.to_pandas() if hasattr(cep_res, "to_pandas") else pd.DataFrame(cep_res)
        print("colunas busca_por_cep:", list(cep_pd.columns))
        print(cep_pd.head(10).to_string())
    except Exception as e:
        print("busca_por_cep existe mas falhou (tente outro nome de arg):", e)
else:
    print("NÃO existe geocodebr.busca_por_cep — procurar equivalente:",
          [a for a in dir(geocodebr) if "cep" in a.lower()])
