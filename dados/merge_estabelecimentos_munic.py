#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_estabelecimentos_munic.py
--------------------------------
Prepara os arquivos para adicionar ao mapa por MUNICÍPIO dois indicadores do
Censo Agropecuário 2017 (IBGE, tabela SIDRA 6754, variável 183):

  - "Estabelecimentos agropecuários"                (tipologia Total = 46302)
  - "Estabelecimentos de agricultura familiar"      (tipologia AF sim = 46304)

Os dados brutos já foram baixados e validados em `estabelecimentos_municipio.csv`
(a soma nacional bate com o oficial: 5.073.324 estabelecimentos). Os totais por
município conferem exatamente com os totais por UF que já estão no site.

O que o script faz:
  1. Baixa o munic.geojson atual do bucket (ou usa um arquivo local, ver --geojson).
  2. Mescla as duas colunas do CSV nas propriedades de cada feature (casadas por ibge7).
  3. Escreve `munic.geojson` pronto para subir no bucket.
  4. Imprime as duas linhas a acrescentar no `indicadores.csv`.

Só a etapa de SUBIR no bucket (Google Cloud) precisa do desenvolvedor — o resto
está automatizado. Uso:

    python3 merge_estabelecimentos_munic.py
    python3 merge_estabelecimentos_munic.py --geojson caminho/local/munic.geojson

Depois: subir o `munic.geojson` gerado e o `indicadores.csv` atualizado no bucket
`storage.googleapis.com/projeto-graficos/ifad2025/mapas/` e trocar o `?v91` da URL
do munic.geojson no index.html por um novo número (ex.: ?v92) para furar o cache.

Municípios sem dado (7, suprimidos pelo IBGE por sigilo estatístico — áreas muito
urbanas como Barueri, Carapicuíba, Nilópolis): ficam sem a propriedade e aparecem
em cinza no mapa. NÃO inventar valor para eles.
"""
import csv, json, os, sys, urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(DIR, "estabelecimentos_municipio.csv")
BUCKET_GEOJSON = "https://storage.googleapis.com/projeto-graficos/ifad2025/mapas/munic.geojson?v91"
OUT_GEOJSON = os.path.join(DIR, "munic.geojson")

IND_TOTAL = "Estabelecimentos agropecuários"
IND_AF = "Estabelecimentos de agricultura familiar"

# Linhas de metadados para o indicadores.csv (intervalos escolhidos pela distribuição;
# ajustáveis se quiser outra quebra de cores no mapa).
INDICADORES_ROWS = [
    [IND_TOTAL, "total", "0, 250, 500, 1000, 2000, 4000, 13000", "Censo Agropecuário 2017, IBGE."],
    [IND_AF,    "total", "0, 150, 350, 700, 1400, 2800, 12000",  "Censo Agropecuário 2017, IBGE."],
]


def load_geojson(path_or_none):
    if path_or_none:
        with open(path_or_none, encoding="utf-8") as f:
            return json.load(f)
    print("Baixando munic.geojson do bucket…")
    with urllib.request.urlopen(BUCKET_GEOJSON, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    geojson_path = None
    if "--geojson" in sys.argv:
        geojson_path = sys.argv[sys.argv.index("--geojson") + 1]

    # 1) Ler o CSV validado
    dados = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dados[row["ibge7"]] = row

    # 2) Carregar geojson e mesclar
    g = load_geojson(geojson_path)
    match = 0
    sem_dado = []
    for feat in g["features"]:
        code = str(int(feat["properties"]["ibge7"]))
        d = dados.get(code)
        if not d:
            sem_dado.append(code)
            continue
        match += 1
        if d["estabelecimentos_total"]:
            feat["properties"][IND_TOTAL] = int(d["estabelecimentos_total"])
        if d["estabelecimentos_agricultura_familiar"]:
            feat["properties"][IND_AF] = int(d["estabelecimentos_agricultura_familiar"])

    # 3) Escrever geojson pronto para subir
    with open(OUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)

    print(f"features: {len(g['features'])} | com dado: {match} | sem dado: {len(sem_dado)}")
    print(f"geojson gravado em: {OUT_GEOJSON}")
    print("\nAcrescentar ao indicadores.csv (uma por linha, no fim do arquivo):\n")
    for r in INDICADORES_ROWS:
        # csv com aspas nos campos que têm vírgula
        print(",".join(f'"{c}"' if "," in c else c for c in r))
    print("\nDepois: subir munic.geojson + indicadores.csv no bucket e furar o cache (?v92 no index.html).")


if __name__ == "__main__":
    main()
