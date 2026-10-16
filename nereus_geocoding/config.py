"""Configuração da pipeline Python (caminhos, regiões, parâmetros).

Espelha o papel de ``config/config_example.R``, adaptado para ler a RAIS
diretamente do banco DuckDB em vez de CSVs por região×ano.
"""

from __future__ import annotations

from pathlib import Path

# ---- Banco / saída ----------------------------------------------------------
DB_RAIS = r"D:\Bases\MTE\RAIS_MTE_BRASIL\rais\db\rais_brasil.duckdb"

# Saída em parquet (1 arquivo por região×ano). Ajuste à vontade.
OUT_DIR = Path(r"D:\Arq-Azzoni\UrbanSprawl\Bases_dados\RAIS_estab\temp_geocoding\parquet_py")

# Cache dos dados do IBGE usados pelo geocodebr (vários GB).
GEOCODEBR_CACHE = Path(r"D:\Arq-Azzoni\UrbanSprawl\Bases_dados\RAIS_estab\temp_geocoding\geocodebr_cache")

# ---- Regiões -> UFs (recorte do projeto, cobre as 27 UFs) -------------------
REGIOES = {
    "sp": ["SP"],
    "mgesrj": ["MG", "ES", "RJ"],
    "sul": ["PR", "SC", "RS"],
    "nordeste": ["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"],
    "norte": ["RO", "AC", "AM", "RR", "PA", "AP", "TO"],
    "centrooeste": ["GO", "MT", "MS", "DF"],
}

ANOS = list(range(2002, 2024))  # 2002..2023 (conforme o banco)

# CRS projetado (metros) para cálculos de distância, por região. 5880 = SIRGAS
# 2000 / Brazil Polyconic (fallback nacional).
REGION_DISTANCE_CRS = {
    "sp": 31983, "mgesrj": 31983, "sul": 31982,
    "centrooeste": 5880, "norte": 5880, "nordeste": 5880,
}
DEFAULT_DISTANCE_CRS = 5880

# ---- Parâmetros de geocoding / qualidade ------------------------------------
SO_ATIVAS = False               # True = só estabelecimentos ativos (indativano)
SD_THRESHOLD_KM = 0.3           # dispersão máx. de CEP aceita (classe 1)
ACCEPT_SINGLE_POINT_CEP = True  # aceita CEP com um único ponto
DEDUP_ENDERECOS = True          # geocodifica cada endereço distinto uma única vez

# ---- Uso de recursos (espelha o script Python original) ---------------------
# Servidor compartilhado: deixa folga para os outros usuários.
MAX_THREADS = 6                 # threads do DuckDB e do geocodebr (~25% de 48)
N_CORES = MAX_THREADS           # alias usado pelo geocodebr
MEMORIA = "32GB"                # limite de memória do DuckDB (usa disco acima disso)

# Teto RÍGIDO do Windows (Job Object) para o processo inteiro, inclusive o
# DuckDB interno do geocodebr: acima disso o Windows nega memória / segura a CPU.
TETO_MEMORIA_GB = 48
TETO_CPU_PCT = 25               # % da CPU total da máquina
PRIORIDADE_BAIXA = True         # processo "abaixo do normal": outros têm preferência

# Antes de cada geocodificação, espera enquanto a máquina estiver ocupada (psutil).
PAUSA_CPU_PCT = 80              # CPU total acima disso -> espera
PAUSA_MEM_LIVRE = 40           # GB livres abaixo disso -> espera
PAUSA_CHECAR_S = 30            # intervalo entre checagens enquanto espera

# Mapeamento de campos (nome lógico -> coluna no DataFrame preparado).
CAMPOS_GEOCODE = {
    "logradouro": "endereco",
    "numero": "numlograd",
    "cep": "cep",
    "localidade": "bairro",
    "municipio": "municipio_7",
    "estado": "uf_dom",
}
