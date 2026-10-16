"""Port Python da pipeline de geocodificação RAIS (nereus_geocoding).

Este pacote traz a lógica de *tratamento de endereço* originalmente escrita em R
(pasta ``R/`` do projeto) para Python, mantendo o comportamento das funções
correspondentes:

Tratamento de endereço (port do R):
- :mod:`nereus_geocoding.standardization`  -> ``R/data_standardization.R``
- :mod:`nereus_geocoding.address_cleaning` -> ``R/address_cleaning.R``
- :mod:`nereus_geocoding.padronizacao`     -> aproximação de ``enderecobr`` (etapa ``pad``)

Pipeline (query no DuckDB -> geocoding -> parquet):
- :mod:`nereus_geocoding.config`     parâmetros, caminhos, regiões->UFs
- :mod:`nereus_geocoding.reader`     leitura/preparo da RAIS no DuckDB
- :mod:`nereus_geocoding.precision`  pontuação de precisão (``R/precision.R``)
- :mod:`nereus_geocoding.geocoding`  5 variantes + melhor (``R/geocode_pipeline.R``)
- :mod:`nereus_geocoding.quality`    filtro de CEP + aceite (``R/quality_filters.R``)
- :mod:`nereus_geocoding.pipeline`   orquestração por região×ano

As funções operam sobre ``pandas.DataFrame`` / ``pandas.Series`` para espelhar o
uso de ``data.table`` no R.
"""

from . import (
    address_cleaning,
    padronizacao,
    standardization,
)

__all__ = [
    "standardization",
    "address_cleaning",
    "padronizacao",
]
