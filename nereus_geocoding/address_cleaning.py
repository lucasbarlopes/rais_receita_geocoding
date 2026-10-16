"""Limpeza de logradouro/número — port de ``R/address_cleaning.R``.

Reimplementa ``logradouro_num_string_fast`` em Python puro (``re``), preservando
o comportamento do original escrito com ``stringi``:

1. separa letra/dígito grudados ("AV5" -> "AV 5");
2. remove variações de "S/N";
3. troca ``.`` e ``,`` por espaço e normaliza espaços;
4. extrai o número do logradouro (último número antes da primeira *stopword*),
   respeitando um número já informado em ``num_col`` (só preenche quando o
   número original é ausente ou zero);
5. remove esse número do texto;
6. opcionalmente corta o texto na primeira *stopword*, em três modos.

A lista :data:`DEFAULT_STOPWORDS` é idêntica à do R (``default_stopwords``).
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "DEFAULT_STOPWORDS",
    "logradouro_num_string",
    "ENDERECO_UPDATE_MODES",
]

# Igual a `default_stopwords` do R (ordem preservada, sem duplicatas).
DEFAULT_STOPWORDS: List[str] = list(dict.fromkeys([
    "sala", "setor", "bloco", "quadra", "bl", "br", "lote", "lt", "qd",
    "conj", "conjunto", "casa", "grupo", "cjto", "fundos", "fund", "cjs",
    "salas", "ap", "apt", "apto", "apartamento", "sl", "zona", "andar",
    "cj", "loja", "galpão", "galpao", "box", "boxe", "pavilhão", "pavilhao",
    "pav", "pça", "prédio", "predio", "area", "are", "entrada", "fundo",
    "subsolo", "sobreloja", "lojas", "zonas", "quadras", "lotes", "setores",
    "blocos", "andars", "apartamentos", "casas", "conjuntos",
    "ponto de referencia", "garage", "terreo", "tereo", "térreo", "andar térreo",
    "andar terreo", "parte", "slj", "quiosque", "piso",
]))

ENDERECO_UPDATE_MODES = (
    "always_cut_on_stopword",
    "cut_when_missing_num",
    "no_cut",
)

# Regexes equivalentes aos usados no R (compilados uma vez).
_RE_LETTER_DIGIT = re.compile(r"([A-Za-z])([0-9])")
_RE_DIGIT_LETTER = re.compile(r"([0-9])([A-Za-z])")
_RE_SN = re.compile(r"\bS\s*[/.\-]?\s*N\b", re.IGNORECASE)
_RE_PUNCT = re.compile(r"[.,]")
_RE_SPACES = re.compile(r"\s+")
_RE_NUMS = re.compile(r"\d{1,5}")
_RE_NUM_BOUNDED = re.compile(r"\b\d{1,5}\b")


def _build_stop_regex(stopwords: Sequence[str]) -> re.Pattern:
    alt = "|".join(re.escape(w) for w in stopwords)
    return re.compile(r"\b(" + alt + r")\b", re.IGNORECASE)


def _norm_spaces(text: str) -> str:
    return _RE_SPACES.sub(" ", text).strip()


def _num_to_token(num: float) -> Optional[str]:
    """Formata um número para uso em regex ``\\b(<num>)\\b`` (sem ``.0`` à toa)."""
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return None
    if isinstance(num, float) and num.is_integer():
        return str(int(num))
    return str(num)


def _clean_one(
    end_orig: Optional[str],
    num_orig: float,
    stop_regex: re.Pattern,
    mode: str,
) -> tuple[str, float]:
    """Processa um único endereço. Retorna (endereco_limpo, numero_novo)."""
    needs_update = (not isinstance(num_orig, (int, float))) or np.isnan(num_orig) or num_orig == 0

    # Qualquer valor não-string (None, pd.NA, NaN, número) vira texto vazio.
    end_work = str(end_orig) if isinstance(end_orig, str) else ""
    end_work = _RE_LETTER_DIGIT.sub(r"\1 \2", end_work)
    end_work = _RE_DIGIT_LETTER.sub(r"\1 \2", end_work)
    end_work = _RE_SN.sub(" ", end_work)
    end_work = _RE_PUNCT.sub(" ", end_work)
    end_work = _norm_spaces(end_work)

    # Texto antes da primeira stopword, para extrair o número.
    m = stop_regex.search(end_work.lower())
    end_for_num = end_work[: m.start()] if m else end_work
    end_for_num = end_for_num.strip()

    nums = _RE_NUMS.findall(end_for_num)
    num_extracted = float(nums[-1]) if nums else np.nan

    num_out = num_orig
    did_replace = needs_update and not np.isnan(num_extracted)
    if did_replace:
        num_out = num_extracted

    # Remove o número escolhido do texto completo (apenas quando houve troca).
    end_no_num = end_work
    if did_replace:
        token = _num_to_token(num_out)
        if token is not None:
            end_no_num = re.sub(r"\b(" + re.escape(token) + r")\b", " ", end_no_num)
    end_no_num = _norm_spaces(end_no_num)

    end_new = end_no_num
    if mode != "no_cut":
        m2 = stop_regex.search(end_no_num.lower())
        do_cut = m2 is not None
        if mode == "cut_when_missing_num":
            do_cut = do_cut and needs_update
        if do_cut:
            pre = end_no_num[: m2.start()]
            pre = _RE_NUM_BOUNDED.sub(" ", pre)
            end_new = _norm_spaces(pre)

    return end_new.strip(), num_out


def logradouro_num_string(
    dt: pd.DataFrame,
    endereco_col: str = "endereco",
    num_col: str = "numlograd",
    new_endereco_col: str = "endereco_limpo",
    new_num_col: str = "numlograd_novo",
    stopwords: Sequence[str] = DEFAULT_STOPWORDS,
    endereco_update_mode: str = "always_cut_on_stopword",
) -> pd.DataFrame:
    """Port de ``logradouro_num_string_fast``.

    Adiciona ``new_endereco_col`` (texto limpo) e ``new_num_col`` (número como
    float, com ``NaN`` para ausente) ao DataFrame recebido (modificado in-place
    e também retornado).

    ``endereco_update_mode`` controla o corte na stopword:

    - ``"no_cut"``: nunca corta;
    - ``"cut_when_missing_num"``: corta só quando o número original era ausente/0;
    - ``"always_cut_on_stopword"``: sempre corta na primeira stopword.
    """
    if endereco_update_mode not in ENDERECO_UPDATE_MODES:
        raise ValueError(
            f"endereco_update_mode deve ser um de {ENDERECO_UPDATE_MODES}, "
            f"recebido: {endereco_update_mode!r}"
        )
    for col in (endereco_col, num_col):
        if col not in dt.columns:
            raise KeyError(f"Column not found: {col}")

    stop_regex = _build_stop_regex(stopwords)

    end_series = dt[endereco_col]
    num_series = pd.to_numeric(dt[num_col], errors="coerce")

    cleaned = [
        _clean_one(e, n, stop_regex, endereco_update_mode)
        for e, n in zip(end_series.tolist(), num_series.tolist())
    ]

    dt[new_endereco_col] = [c[0] for c in cleaned]
    dt[new_num_col] = [c[1] for c in cleaned]
    return dt
