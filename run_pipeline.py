"""Roda a pipeline de geocodificação da RAIS (query no DuckDB -> parquet).

Exemplos:
    # teste pequeno: 1 região, 1 ano, só 2000 estabelecimentos
    python run_pipeline.py --regioes sp --anos 2023 --limite 2000

    # uma região inteira, um ano
    python run_pipeline.py --regioes sp --anos 2023

    # tudo (todas as regiões e anos) -- MUITO pesado
    python run_pipeline.py

    # refazer (sobrescrever) parquets já gerados
    python run_pipeline.py --regioes sp --anos 2023 --overwrite

Saída: um parquet por região×ano em OUT_DIR (ver config.py).
"""

import argparse
import sys

from nereus_geocoding import config, pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regioes", help="lista separada por vírgula (padrão: todas)",
                    default=None)
    ap.add_argument("--anos", help="lista separada por vírgula (padrão: todos)",
                    default=None)
    ap.add_argument("--limite", type=int, default=None,
                    help="máx. de estabelecimentos por região×ano (teste)")
    ap.add_argument("--overwrite", action="store_true",
                    help="refaz parquets já existentes")
    ap.add_argument("--nome-municipio", action="store_true",
                    help="usa o NOME do município (de rais.municipios) em vez do código")
    args = ap.parse_args()

    regioes = [r.strip() for r in args.regioes.split(",")] if args.regioes else None
    anos = [int(a) for a in args.anos.split(",")] if args.anos else None

    if regioes:
        invalidas = [r for r in regioes if r not in config.REGIOES]
        if invalidas:
            sys.exit(f"Regiões inválidas: {invalidas}. Opções: {list(config.REGIOES)}")

    feitos = pipeline.run_all(
        regioes=regioes, anos=anos, limite=args.limite,
        overwrite=args.overwrite, usar_nome_municipio=args.nome_municipio,
    )
    print(f"\nConcluído. {len(feitos)} arquivo(s) gravado(s) em {config.OUT_DIR}")


if __name__ == "__main__":
    main()
