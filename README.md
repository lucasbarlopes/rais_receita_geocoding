# RAIS / Receita — Geocodificação

Geocodificação em massa dos endereços de estabelecimentos da **RAIS** (e, futuramente, da **Receita Federal**) para todo o Brasil, usando o [`geocodebr`](https://pypi.org/project/geocodebr/) (dados do CNEFE/IBGE) como primeira passada — método rápido e barato. Os endereços que não ficarem bons serão, numa etapa posterior, reprocessados por outros meios.

O código Python em `nereus_geocoding/` é um **port** de uma pipeline originalmente escrita em R (as docstrings referenciam os arquivos `R/*.R` de origem), adaptado para ler a RAIS direto de um banco **DuckDB** em vez de CSVs por região×ano.

---

## Como funciona

Para cada estabelecimento, a pipeline geocodifica **5 variantes** do endereço e fica com a de melhor precisão:

| variante | descrição |
|----------|-----------|
| `raw`    | campos crus (endereço, número, CEP, bairro, município, UF) |
| `pad`    | campos padronizados pelo `enderecobr` (via `geocodebr`) |
| `lns_0`  | logradouro+número sobre o `pad`, modo `no_cut` |
| `lns_1`  | idem, modo `cut_when_missing_num` |
| `lns_2`  | idem, modo `always_cut_on_stopword` |

A melhor variante por estabelecimento é a de menor *score* de precisão (empate → última variante da ordem). Em seguida, aplica-se o **filtro de aceite**:

- **classe 0** — precisão boa (número/logradouro): **aceita** direto.
- **classe 1** — precisão de CEP (`dc01`/`dc02`): aceita **só** se o CEP for consistente (dispersão dos pontos do CEP abaixo do limiar, ou CEP de ponto único).
- **classe 2** — precisão baixa (bairro/município, `db01`/`dm01`): **rejeitada**.
- **sem resultado** — nenhuma variante geocodificou: rejeitada.

A coluna `aceito` (1/0) resume o resultado.

---

## Estrutura do repositório

```
nereus_geocoding/           pacote principal (port do R)
├── config.py               caminhos, regiões→UFs, parâmetros, tetos de recurso
├── reader.py               leitura/preparo da RAIS no DuckDB
├── standardization.py      padronização de campos (ibge6→7, UF, CEP sentinela)
├── padronizacao.py         aproximação do enderecobr + ponte para o enderecobr real
├── address_cleaning.py     limpeza de logradouro/número (variantes lns_*)
├── precision.py            score e classe de precisão
├── geocoding.py            orquestra as 5 variantes e escolhe a melhor
├── quality.py              filtro de consistência de CEP e aceite
├── pipeline.py             orquestração por região×ano → parquet
└── recursos.py             limitação de CPU/memória (Windows Job Object + psutil)

run_pipeline.py             CLI da pipeline
resumo_qualidade.py         resumo no console (por região×ano e agregado)
resumo_excel.py             gera Excel com resumo da precisão por UF×ano
demo_tratamento_endereco.py demonstração do tratamento de endereço (amostra sintética)
inspecionar_rais.py         inspeciona o schema do banco DuckDB da RAIS
probe_geocodebr.py          sonda a API do geocodebr (colunas/precisão)
probe_enderecobr.py         sonda o enderecobr embutido no geocodebr
requirements.txt            dependências
```

---

## Requisitos e instalação

Python 3.13 (há uma `.venv` no repositório). Instale as dependências na env:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt geocodebr duckdb pyarrow psutil polars openpyxl
```

- `geocodebr`, `duckdb`, `pyarrow`, `psutil`, `polars` são usadas pela pipeline, mas **não** estavam no `requirements.txt` original.
- `openpyxl` é necessária apenas para `resumo_excel.py`.
- No primeiro uso, o `geocodebr` baixa os dados do CNEFE (vários GB) para a pasta de cache definida em `config.py`.

Para conferir que nada falta:

```powershell
.venv\Scripts\python.exe -c "from nereus_geocoding import config, pipeline; print('imports OK')"
```

---

## Configuração — `nereus_geocoding/config.py`

Ajuste antes de rodar:

- `DB_RAIS` — caminho do banco DuckDB da RAIS.
- `OUT_DIR` — pasta de saída dos parquets (1 por região×ano).
- `GEOCODEBR_CACHE` — cache dos dados do IBGE usados pelo `geocodebr`.
- `REGIOES` — mapeamento região → lista de UFs (cobre as 27 UFs):

  | chave | UFs |
  |-------|-----|
  | `sp` | SP |
  | `mgesrj` | MG, ES, RJ |
  | `sul` | PR, SC, RS |
  | `nordeste` | MA, PI, CE, RN, PB, PE, AL, SE, BA |
  | `norte` | RO, AC, AM, RR, PA, AP, TO |
  | `centrooeste` | GO, MT, MS, DF |

- `ANOS` — intervalo de anos (padrão 2002–2023).
- Parâmetros de qualidade: `SD_THRESHOLD_KM`, `ACCEPT_SINGLE_POINT_CEP`, `SO_ATIVAS`, `DEDUP_ENDERECOS`.
- Tetos de recurso (servidor compartilhado): `MAX_THREADS`, `MEMORIA`, `TETO_MEMORIA_GB`, `TETO_CPU_PCT`, `PRIORIDADE_BAIXA`, e a pausa automática (`PAUSA_*`).

---

## Rodando a pipeline

```powershell
# teste pequeno: 1 região, 1 ano, só 2000 estabelecimentos
.venv\Scripts\python.exe run_pipeline.py --regioes sp --anos 2023 --limite 2000

# uma região inteira, um ano
.venv\Scripts\python.exe run_pipeline.py --regioes sp --anos 2023

# várias regiões (Brasil menos SP), todos os anos
.venv\Scripts\python.exe run_pipeline.py --regioes mgesrj,sul,nordeste,norte,centrooeste

# tudo (todas as regiões e anos) — muito pesado
.venv\Scripts\python.exe run_pipeline.py
```

Opções:

- `--regioes` — lista separada por vírgula (padrão: todas).
- `--anos` — lista separada por vírgula (padrão: todos).
- `--limite` — máx. de estabelecimentos por região×ano (para testes).
- `--overwrite` — refaz parquets já existentes.
- `--nome-municipio` — usa o **nome** do município (de `rais.municipios`) em vez do código.

**Retomada automática:** a pipeline pula região×ano cujo parquet já existe (a menos de `--overwrite`). Se for interrompida, basta rodar o mesmo comando que ela continua de onde parou.

### Saída

Um parquet por região×ano em `OUT_DIR` (ex.: `sp_2023.parquet`), com uma linha por estabelecimento. Colunas principais:

- **Identificação / metadados:** `regiao`, `id`, `identificad_m`, `ano`, `uf`, `municipio`, `municipio_7`, `uf_dom`, `cep`, `bairro`, `numlograd`, `estoque`, `matrizfilial`, `clascnae20`, `endereco`.
- **Geocodificação:** `best_step` (variante vencedora), `endereco_best`, `endereco_fonte`, `precisao_best` (código, ex. `da01`), `best_score`, `precisao_cat` (categoria: número/logradouro/CEP/…), `lat`, `lon`, `desvio_metros`, `endereco_encontrado`, `cep_padr`.
- **Qualidade:** `classe` (0/1/2 ou nulo), `aceito` (1/0).

---

## Resumos de qualidade

Console (por região×ano e agregado):

```powershell
.venv\Scripts\python.exe resumo_qualidade.py
```

Excel com a precisão **por UF × ano** (grava `resumo_precisao_uf_ano.xlsx` na própria `OUT_DIR`):

```powershell
.venv\Scripts\python.exe resumo_excel.py
# ou um caminho customizado:
.venv\Scripts\python.exe resumo_excel.py --out "D:\caminho\resumo.xlsx"
```

Abas geradas: `uf_ano` (linhas, aceitas, % aceito e distribuição por classe), `pct_aceito` (matriz UF × ano), `precisao_cat_pct` (% por categoria de precisão) e `legenda`.

---

## Notas de execução (Windows / servidor compartilhado)

- O processo roda em **prioridade abaixo do normal** e sob um **Job Object** com teto rígido de memória e CPU (`recursos.py`), para não atrapalhar outros usuários do servidor. Antes de cada geocodificação, espera a máquina ter folga de CPU/RAM (`psutil`).
- O `geocodebr` avisa sobre *heap NT legacy* no Windows (impacto só de performance). Para acelerar, é possível gerar um interpretador com Segment Heap: `python -m geocodebr._heap_patch` (opcional; ver README do geocodebr).
- O aviso `Alguns números não puderam ser convertidos para integer` vem do `enderecobr` tratando números de logradouro ausentes/"S/N" — é esperado, não é erro.

---

## Limitações conhecidas

- **Padronização aproximada:** `padronizacao.py` tem uma aproximação em Python do `enderecobr`, usada como *fallback*. Por padrão a pipeline usa o **`enderecobr` real** (via `geocodebr`); a aproximação não reproduz o original caractere a caractere (sem metaphone, dicionário de abreviações reduzido, etc.).
- A consistência de CEP usa distância de *haversine* (em vez de projeção métrica); a diferença é desprezível na escala de um CEP.

---

## Próximos passos (to-do)

- Disponibilizar no servidor o caminho da RAIS/Receita em parquet.
- Integrar a base da **Receita Federal** (mesma lógica de geocodificação).
- Segunda etapa: reprocessar os endereços **não aceitos** por outros métodos de geocodificação.
