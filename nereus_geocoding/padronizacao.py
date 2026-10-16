"""Padronização de endereços — APROXIMAÇÃO em Python do pacote R ``enderecobr``.

A pipeline R usa ``enderecobr::padronizar_enderecos`` (etapa ``pad``) para gerar
as colunas ``logradouro_padr``, ``numero_padr``, ``cep_padr``, ``bairro_padr``,
``municipio_padr`` e ``estado_padr``, que alimentam a variante ``pad`` e as
variantes ``lns_*`` do geocoding.

A lógica real do ``enderecobr`` vive no crate Rust ``enderecobr_rs`` (0.3.0),
com dezenas/centenas de regras de regex e tabelas de dados (município IBGE,
metaphone, número por extenso). **Este módulo é uma APROXIMAÇÃO** — cobre o
grosso dos casos (uppercase, remoção de acentos, normalização de espaços,
expansão das abreviações mais comuns de tipo de logradouro e de títulos,
normalização de rodovias BR/UF, número e CEP), mas NÃO reproduz o enderecobr
caractere a caractere.

Divergências conhecidas em relação ao enderecobr
-------------------------------------------------
- Logradouro: o dicionário de expansões aqui é um subconjunto; não há metaphone
  nem correção fonética de erros de grafia; nomes por extenso de datas e de
  pessoas (Getúlio Vargas, JK etc.) não são tratados.
- Município: o enderecobr mapeia o código IBGE para o NOME oficial. Aqui, por
  padrão, o código de 7 dígitos é repassado como string (o geocodebr aceita
  código no campo ``municipio``). Passe ``cod_to_nome`` para obter o nome.
- Estado: o enderecobr, por padrão, devolve o nome por extenso. Aqui o padrão é
  a SIGLA (que o geocodebr aceita). Use ``formato="por_extenso"`` para o nome.
- CEP: devolvido como 8 dígitos (sem hífen); o enderecobr formata ``#####-###``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Mapping, Optional

import pandas as pd

__all__ = [
    "padronizar_logradouros",
    "padronizar_numeros",
    "padronizar_ceps",
    "padronizar_bairros",
    "padronizar_municipios",
    "padronizar_estados",
    "padronizar_enderecos",
    "padronizar_enderecos_real",
    "TIPOS_LOGRADOURO",
    "TITULOS",
    "SIGLA_TO_NOME",
]

# Colunas *_padr que a pipeline de geocoding consome.
_COLS_PADR = [
    "logradouro_padr", "numero_padr", "cep_padr",
    "bairro_padr", "municipio_padr", "estado_padr",
]


def padronizar_enderecos_real(
    df: pd.DataFrame,
    formato_estados: str = "sigla",
    formato_numeros: str = "character",
) -> pd.DataFrame:
    """Padronização FIEL via ``geocodebr.enderecobr_padronizar_enderecos`` (enderecobr real).

    Usa o enderecobr embutido no geocodebr (que opera em polars). Espera que
    ``df`` tenha as colunas ``endereco, numlograd, cep, bairro, municipio_7,
    uf_dom`` e devolve uma cópia de ``df`` com as colunas
    :data:`_COLS_PADR` adicionadas.

    Requer ``polars`` e ``geocodebr`` instalados (ambos já são dependências do
    geocoding). Levanta ``ImportError`` se faltarem.
    """
    import geocodebr  # noqa: F401
    import polars as pl

    campos = {
        "logradouro": "endereco",
        "numero": "numlograd",
        "cep": "cep",
        "localidade": "bairro",
        "municipio": "municipio_7",
        "estado": "uf_dom",
    }
    entrada = df[list(campos.values())].astype("string")
    pl_in = pl.from_pandas(entrada)
    pl_out = geocodebr.enderecobr_padronizar_enderecos(
        pl_in, campos,
        formato_estados=formato_estados,
        formato_numeros=formato_numeros,
        manter_cols_extras=False,
    )
    out_pd = pl_out.to_pandas()
    # o campo "localidade" vira "localidade_padr"; renomeia para bairro_padr.
    if "localidade_padr" in out_pd.columns and "bairro_padr" not in out_pd.columns:
        out_pd = out_pd.rename(columns={"localidade_padr": "bairro_padr"})

    res = df.copy()
    faltando = [c for c in _COLS_PADR if c not in out_pd.columns]
    if faltando:
        raise RuntimeError(
            f"enderecobr não devolveu as colunas esperadas: faltam {faltando}; "
            f"recebidas: {list(out_pd.columns)}"
        )
    for col in _COLS_PADR:
        res[col] = out_pd[col].values
    return res

# Abreviação (início do logradouro) -> forma por extenso.
TIPOS_LOGRADOURO: Dict[str, str] = {
    "R": "RUA", "RUA": "RUA", "AV": "AVENIDA", "AVN": "AVENIDA", "AVD": "AVENIDA",
    "AVENIDA": "AVENIDA", "AL": "ALAMEDA", "ROD": "RODOVIA", "RDV": "RODOVIA",
    "EST": "ESTRADA", "ESTR": "ESTRADA", "ETR": "ESTRADA", "TV": "TRAVESSA",
    "TRV": "TRAVESSA", "TR": "TRAVESSA", "PC": "PRACA", "PCA": "PRACA", "PRC": "PRACA",
    "LG": "LARGO", "LGO": "LARGO", "LRG": "LARGO", "VD": "VIADUTO", "VIAD": "VIADUTO",
    "BC": "BECO", "BE": "BECO", "SRV": "SERVIDAO", "VLA": "VIELA", "CAM": "CAMINHO",
    "ACS": "ACESSO", "MARG": "MARGINAL", "LOT": "LOTEAMENTO", "SIT": "SITIO",
    "FAZ": "FAZENDA", "CH": "CHACARA", "Q": "QUADRA", "QD": "QUADRA", "QR": "QUADRA",
    "CJ": "CONJUNTO", "CONJ": "CONJUNTO", "PQ": "PARQUE", "JD": "JARDIM", "VL": "VILA",
    "LAD": "LADEIRA", "LD": "LADEIRA", "NUC": "NUCLEO", "LOC": "LOCALIDADE",
    "MR": "MORRO", "MO": "MORRO", "FV": "FAVELA", "CAN": "CANAL", "CB": "CABO",
    "PTE": "PONTE", "ESC": "ESCOLA", "TUN": "TUNEL", "SER": "SERRA", "CPO": "CAMPO",
    "COL": "COLONIA",
}

# Títulos (em qualquer posição) -> forma por extenso.
TITULOS: Dict[str, str] = {
    "DR": "DOUTOR", "DRA": "DOUTORA", "PROF": "PROFESSOR", "PROFA": "PROFESSORA",
    "CEL": "CORONEL", "GAL": "GENERAL", "GEN": "GENERAL", "MAL": "MARECHAL",
    "CAP": "CAPITAO", "TEN": "TENENTE", "SGT": "SARGENTO", "SARG": "SARGENTO",
    "BRIG": "BRIGADEIRO", "ALM": "ALMIRANTE", "MAJ": "MAJOR", "SOLD": "SOLDADO",
    "PRES": "PRESIDENTE", "SEN": "SENADOR", "DEP": "DEPUTADO", "VER": "VEREADOR",
    "GOV": "GOVERNADOR", "PREF": "PREFEITO", "MIN": "MINISTRO", "ENG": "ENGENHEIRO",
    "ENGA": "ENGENHEIRA", "COM": "COMENDADOR", "CDOR": "COMENDADOR", "PE": "PADRE",
    "MONS": "MONSENHOR", "STA": "SANTA", "STO": "SANTO",
}

SIGLA_TO_NOME: Dict[str, str] = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPA", "AM": "AMAZONAS", "BA": "BAHIA",
    "CE": "CEARA", "DF": "DISTRITO FEDERAL", "ES": "ESPIRITO SANTO", "GO": "GOIAS",
    "MA": "MARANHAO", "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS", "PA": "PARA", "PB": "PARAIBA", "PR": "PARANA",
    "PE": "PERNAMBUCO", "PI": "PIAUI", "RJ": "RIO DE JANEIRO",
    "RN": "RIO GRANDE DO NORTE", "RS": "RIO GRANDE DO SUL", "RO": "RONDONIA",
    "RR": "RORAIMA", "SC": "SANTA CATARINA", "SP": "SAO PAULO", "SE": "SERGIPE",
    "TO": "TOCANTINS",
}
_NOME_TO_SIGLA = {v: k for k, v in SIGLA_TO_NOME.items()}
_UF_SIGLAS = set(SIGLA_TO_NOME)

_RE_SPACES = re.compile(r"\s+")
_RE_COMBINING = re.compile(r"[̀-ͯ]")


def _strip_accents(text: str) -> str:
    return _RE_COMBINING.sub("", unicodedata.normalize("NFKD", text))


def _as_upper_clean(series: pd.Series) -> pd.Series:
    """Texto -> MAIÚSCULAS, sem acento, pontuação virando espaço, espaços simples."""
    s = series.astype("string")
    s = s.map(lambda x: _strip_accents(x) if isinstance(x, str) else x)
    s = s.str.upper()
    s = s.str.replace(r"\\", "/", regex=True)
    s = s.str.replace(r"[^A-Z0-9/&\- ]", " ", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    return s


# Padrões como string (compatível com pandas Series.str.replace(..., regex=True)).
_TITULO_KEYS = sorted(TITULOS, key=len, reverse=True)
_PAT_TITULOS = r"\b(" + "|".join(map(re.escape, _TITULO_KEYS)) + r")\b"
# Regex de tipo no início: ^(RUA|AV|...)\b — usado via re.sub por elemento.
_TIPO_KEYS = sorted(TIPOS_LOGRADOURO, key=len, reverse=True)
_RE_TIPO_INICIO = re.compile(r"^(" + "|".join(map(re.escape, _TIPO_KEYS)) + r")\b")
_PAT_BR = r"\bBR[-\s]?(\d{3})\b"
_PAT_UF_ROD = r"\b(" + "|".join(sorted(_UF_SIGLAS)) + r")[-\s]?(\d{3})\b"
_PAT_OUTROS = r"^OUTROS\s+"


def _expand_tipo_inicio(text: str) -> str:
    return _RE_TIPO_INICIO.sub(lambda m: TIPOS_LOGRADOURO[m.group(1)], text, count=1)


def padronizar_logradouros(series: pd.Series) -> pd.Series:
    """Aproximação de ``enderecobr::padronizar_logradouros`` (ver divergências no topo)."""
    s = _as_upper_clean(series)
    s = s.str.replace(_PAT_OUTROS, "", regex=True)
    s = s.map(lambda x: _expand_tipo_inicio(x) if isinstance(x, str) else x)
    s = s.str.replace(_PAT_TITULOS, lambda m: TITULOS[m.group(1)], regex=True)
    s = s.str.replace(_PAT_BR, r"BR-\1", regex=True)
    s = s.str.replace(_PAT_UF_ROD, r"\1-\2", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    s = s.replace("", pd.NA)
    return s


_RE_DIGITS = re.compile(r"\d+")


def _num_one(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "S/N"
    txt = str(x).upper()
    nums = _RE_DIGITS.findall(txt)
    if not nums:
        return "S/N"
    # primeiro bloco de dígitos, sem zeros à esquerda
    val = nums[0].lstrip("0")
    return val if val else "S/N"


def padronizar_numeros(series: pd.Series, formato: str = "por_extenso") -> pd.Series:
    """Aproximação de ``padronizar_numeros``: devolve o número como string ou ``"S/N"``.

    ``formato`` é aceito por compatibilidade de assinatura, mas ignorado nesta
    aproximação (o enderecobr suporta número por extenso, aqui não).
    """
    return series.map(_num_one).astype("string")


def padronizar_ceps(series: pd.Series) -> pd.Series:
    """CEP como 8 dígitos (sem hífen); inválido -> NA. (enderecobr formata ``#####-###``.)"""
    s = series.astype("string").str.replace(r"\.0$", "", regex=True)
    s = s.str.replace(r"\D", "", regex=True).str.zfill(8)
    s = s.where(s.str.fullmatch(r"\d{8}") & (s != "00000000"), other=pd.NA)
    return s


def padronizar_bairros(series: pd.Series) -> pd.Series:
    """Aproximação de ``padronizar_bairros``: maiúsculas, sem acento, espaços simples."""
    s = _as_upper_clean(series)
    s = s.replace("", pd.NA)
    return s


def padronizar_municipios(
    series: pd.Series, cod_to_nome: Optional[Mapping[str, str]] = None
) -> pd.Series:
    """Aproximação de ``padronizar_municipios``.

    Por padrão repassa o código (7 dígitos) como string — o geocodebr aceita
    código no campo ``municipio``. Se ``cod_to_nome`` for fornecido (ex.: tabela
    ``rais.municipios``), mapeia código -> nome padronizado (maiúsculas, sem acento).
    """
    s = series.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    if cod_to_nome is None:
        return s.where(s != "", other=pd.NA)
    mapa = {str(k): _strip_accents(str(v)).upper() for k, v in cod_to_nome.items()}
    return s.map(lambda c: mapa.get(c, pd.NA) if c else pd.NA).astype("string")


def padronizar_estados(series: pd.Series, formato: str = "sigla") -> pd.Series:
    """Aproximação de ``padronizar_estados``.

    Aceita sigla, nome por extenso ou código numérico de UF na entrada.
    ``formato="sigla"`` (padrão aqui) devolve a sigla; ``"por_extenso"`` devolve o
    nome. (No enderecobr o padrão é ``por_extenso``.)
    """
    from .standardization import UF_MAP  # código numérico -> sigla

    def _one(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return pd.NA
        t = _strip_accents(str(x)).upper().strip()
        if t in _UF_SIGLAS:
            sigla = t
        elif t in _NOME_TO_SIGLA:
            sigla = _NOME_TO_SIGLA[t]
        else:
            digits = re.sub(r"\D", "", t)
            sigla = UF_MAP.get(digits.zfill(2)) if digits else None
        if sigla is None:
            return pd.NA
        return sigla if formato == "sigla" else SIGLA_TO_NOME[sigla]

    return series.map(_one).astype("string")


# Mapa campo -> função de padronização (os campos que a pipeline usa).
_FIELD_FUNCS = {
    "logradouro": padronizar_logradouros,
    "numero": padronizar_numeros,
    "cep": padronizar_ceps,
    "bairro": padronizar_bairros,
    "municipio": padronizar_municipios,
    "estado": padronizar_estados,
}


def padronizar_enderecos(
    df: pd.DataFrame,
    campos: Mapping[str, str],
    formato_estados: str = "sigla",
    formato_numeros: str = "por_extenso",
    cod_to_nome: Optional[Mapping[str, str]] = None,
) -> pd.DataFrame:
    """Aproximação de ``enderecobr::padronizar_enderecos``.

    ``campos`` mapeia nome-do-campo -> coluna no DataFrame, por exemplo::

        {"logradouro": "endereco", "numero": "numlograd", "cep": "cep",
         "bairro": "bairro", "municipio": "municipio_7", "estado": "uf_dom"}

    Para cada campo presente, cria a coluna ``<campo>_padr``. Modifica e devolve
    uma cópia do DataFrame recebido.
    """
    out = df.copy()
    for campo, col in campos.items():
        if campo not in _FIELD_FUNCS:
            continue
        if col not in out.columns:
            raise KeyError(f"Column not found for field {campo!r}: {col}")
        func = _FIELD_FUNCS[campo]
        if campo == "estado":
            res = func(out[col], formato=formato_estados)
        elif campo == "numero":
            res = func(out[col], formato=formato_numeros)
        elif campo == "municipio":
            res = func(out[col], cod_to_nome=cod_to_nome)
        else:
            res = func(out[col])
        out[f"{campo}_padr"] = res
    return out
