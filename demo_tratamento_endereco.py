"""Demonstração rápida do tratamento de endereço portado do R.

Rodar a partir da pasta ``python/`` do projeto:

    cd python
    python demo_tratamento_endereco.py

Requer: pandas, numpy  (pip install pandas numpy)
"""

import pandas as pd

from nereus_geocoding import address_cleaning, padronizacao, standardization

# Amostra sintética no formato de entrada da RAIS.
df = pd.DataFrame({
    "endereco": [
        "AV. PAULISTA 1578 APTO 52",
        "R PROF JOSE NICOLI S/N BLOCO B",
        "ESTR DO CATINGUEIRO, 12345 - FUNDOS",
        "RODOVIA BR 101 KM 23",
        None,
    ],
    "numlograd": [0, None, 999, None, 10],
    "cep": ["01310100", "1310100", "99999999", None, "04567000"],
    "municipio_6": ["355030", "355030", "330455", "292740", "150140"],
    "cduf": ["35", "35", "33", "29", "15"],
    "bairro": ["Bela Vista", "Centro", None, "Zona Rural", "Jardim das Flores"],
})

print("=" * 70)
print("1) PADRONIZAÇÃO DE CAMPOS  (standardization.py  <- data_standardization.R)")
print("=" * 70)

# IBGE 6 -> 7 dígitos (dígito verificador)
df["municipio_7"] = standardization.ibge6_to_7(df["municipio_6"])
# Código numérico de UF -> sigla
standardization.add_sigla_from_uf(df, "cduf", "uf_dom")
# CEP sentinela 99999999 -> NA (exceto município 412625)
standardization.change_cep_99999999_to_na(df, "cep", "municipio_6")

print(df[["municipio_6", "municipio_7", "cduf", "uf_dom", "cep"]].to_string(index=False))

print()
print("=" * 70)
print("2) LIMPEZA LOGRADOURO/NÚMERO  (address_cleaning.py  <- address_cleaning.R)")
print("=" * 70)

for mode in address_cleaning.ENDERECO_UPDATE_MODES:
    tmp = address_cleaning.logradouro_num_string(
        df.copy(), endereco_col="endereco", num_col="numlograd",
        endereco_update_mode=mode,
    )
    print(f"\n-- modo: {mode}")
    print(tmp[["endereco", "numlograd", "endereco_limpo", "numlograd_novo"]].to_string(index=False))

print()
print("=" * 70)
print("3) PADRONIZAÇÃO ESTILO enderecobr  (padronizacao.py  -- APROXIMAÇÃO)")
print("=" * 70)

campos = {
    "logradouro": "endereco",
    "numero": "numlograd",
    "cep": "cep",
    "bairro": "bairro",
    "municipio": "municipio_7",
    "estado": "uf_dom",
}
dfp = padronizacao.padronizar_enderecos(df, campos)
cols_padr = [f"{c}_padr" for c in campos]
print(dfp[["endereco"] + cols_padr].to_string(index=False))
