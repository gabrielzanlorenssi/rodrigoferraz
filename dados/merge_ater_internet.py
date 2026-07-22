#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_ater_internet.py
----------------------
Junta ao mapa dois blocos novos de indicadores, por MUNICÍPIO e por UF:

  A) Acesso a orientação técnica (SIDRA 6881, Censo Agropecuário 2017)
     - "% que recebe orientação técnica" = recebe / total de estabelecimentos
     - um indicador por origem (governo, próprio produtor, cooperativas, empresas
       integradoras, empresas privadas, ONGs, Sistema S, outra) como % do total.
       Um estabelecimento pode ter mais de uma origem -> os % não somam 100%.
  B) "% de domicílios com acesso à internet" (SIDRA 9936, Censo Demográfico 2022)
     = domicílios com internet / domicílios particulares permanentes ocupados.

Entradas (geradas por baixar_ater_orientacao.py e baixar_internet_censo2022.py):
  dados/ater_orientacao_municipio.csv, dados/ater_orientacao_uf.csv
  dados/internet_municipio.csv,        dados/internet_uf.csv

Saídas:
  dados/munic.geojson       — geojson do bucket + novas propriedades (% em decimal 0–1)
  dados/indicadores.csv     — indicadores.csv do bucket + novas linhas de metadados
  dados/UF_PCT_snippet.js   — objeto JS UF_PCT para colar no index.html (nível UF)

Municípios sem dado (sigilo do IBGE) ficam sem a propriedade -> cinza no mapa.
NÃO inventar valor. Uso:  python3 merge_ater_internet.py
"""
import csv, json, os, urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
BUCKET = "https://storage.googleapis.com/ict4dbrazil/mapas/"

# indicador -> coluna do CSV de ATER (numerador); denominador é sempre "total"
ATER_INDIC = [
    ("% que recebe orientação técnica",              "recebe"),
    ("% orientação técnica: governo",                "governo"),
    ("% orientação técnica: próprio produtor",       "propria"),
    ("% orientação técnica: cooperativas",           "cooperativas"),
    ("% orientação técnica: empresas integradoras",  "integradoras"),
    ("% orientação técnica: empresas privadas",      "privadas"),
    ("% orientação técnica: ONGs",                   "ong"),
    ("% orientação técnica: Sistema S",              "sistema_s"),
    ("% orientação técnica: outra origem",           "outra"),
]
INTERNET_INDIC = "% de domicílios com acesso à internet"

FONTE_ATER_RECEBE = "IBGE, Censo Agropecuário 2017 (tabela 6881)."
FONTE_ATER_ORIGEM = ("IBGE, Censo Agropecuário 2017 (tabela 6881). Um estabelecimento "
                     "pode receber orientação de mais de uma origem; os percentuais "
                     "não somam 100%.")
FONTE_INTERNET = "IBGE, Censo Demográfico 2022."

UF_SIGLA = {"11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO",
            "21":"MA","22":"PI","23":"CE","24":"RN","25":"PB","26":"PE","27":"AL",
            "28":"SE","29":"BA","31":"MG","32":"ES","33":"RJ","35":"SP","41":"PR",
            "42":"SC","43":"RS","50":"MS","51":"MT","52":"GO","53":"DF"}


def read_csv(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(s):
    s = (s or "").strip()
    return int(s) if s not in ("", "-") else None


def ratio(numer, denom):
    if numer is None or denom in (None, 0):
        return None
    return numer / denom


def quantile_breaks(vals, nbins=6):
    """6 faixas -> 7 pontos de corte, por quantis. Decimais arredondados.

    Distribuições com muitos zeros (SIDRA '-' = zero absoluto): a 1ª faixa fica
    para os ~zero e os quantis são calculados só sobre os positivos — senão os
    cortes degeneram (vários quantis iguais a 0) e o mapa perde a gradação.
    """
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return "0, 0.2, 0.4, 0.6, 0.8, 0.9, 1"
    pos = [v for v in xs if v > 0]
    muitos_zeros = len(pos) < len(xs) * 0.9 and len(pos) > nbins
    base = pos if muitos_zeros else xs
    pts = [0.0] if muitos_zeros else []
    n_q = nbins - 1 if muitos_zeros else nbins  # nº de intervalos sobre a base
    for i in range(n_q + 1):
        q = i / n_q
        idx = min(len(base) - 1, int(round(q * (len(base) - 1))))
        pts.append(base[idx])
    # arredonda para 3 casas, garante monotonicidade e extremos limpos
    out, prev = [], -1
    for i, v in enumerate(pts):
        r = round(v, 3)
        if r <= prev:
            r = round(prev + 0.001, 3)
        out.append(r)
        prev = r
    # piso = mínimo real (arredondado para baixo em 2 casas), como nos demais % do mapa
    import math
    out[0] = max(0.0, math.floor(xs[0] * 100) / 100)
    out[-1] = max(out[-1], round(xs[-1], 3))
    return ", ".join(("%g" % v) for v in out)


def main():
    # ---------- Município ----------
    ater_mun = {r["ibge7"]: r for r in read_csv("ater_orientacao_municipio.csv")}
    net_mun = {r["ibge7"]: r for r in read_csv("internet_municipio.csv")}

    # calcula percentuais municipais e guarda para os breaks
    dist = {nome: [] for nome, _ in ATER_INDIC}
    dist[INTERNET_INDIC] = []
    props_por_ibge = {}
    for ibge7, r in ater_mun.items():
        tot = num(r["total"])
        d = props_por_ibge.setdefault(ibge7, {})
        for nome, col in ATER_INDIC:
            v = ratio(num(r[col]), tot)
            if v is not None:
                d[nome] = round(v, 6)
                dist[nome].append(v)
    for ibge7, r in net_mun.items():
        v = ratio(num(r["domicilios_com_internet"]), num(r["domicilios_total"]))
        if v is not None:
            props_por_ibge.setdefault(ibge7, {})[INTERNET_INDIC] = round(v, 6)
            dist[INTERNET_INDIC].append(v)

    # mescla no geojson do bucket
    print("Baixando munic.geojson do bucket…")
    with urllib.request.urlopen(BUCKET + "munic.geojson?v93", timeout=180) as resp:
        g = json.loads(resp.read().decode("utf-8"))
    match = 0
    for feat in g["features"]:
        code = str(int(feat["properties"]["ibge7"]))
        extra = props_por_ibge.get(code)
        if extra:
            feat["properties"].update(extra)
            match += 1
    out_geo = os.path.join(DIR, "munic.geojson")
    with open(out_geo, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)
    print(f"  geojson: {len(g['features'])} features | com dados novos: {match} -> {out_geo}")

    # ---------- indicadores.csv (bucket + novas linhas) ----------
    print("Baixando indicadores.csv do bucket…")
    with urllib.request.urlopen(BUCKET + "indicadores.csv?v93", timeout=120) as resp:
        base_rows = list(csv.reader(resp.read().decode("utf-8").splitlines()))
    header, body = base_rows[0], base_rows[1:]
    # Idempotência: se o bucket já tiver versões destas linhas, remove antes de
    # acrescentar as recalculadas (senão duplica a cada re-execução)
    nomes_novos = set(n for n, _ in ATER_INDIC) | {INTERNET_INDIC}
    body = [r for r in body if r and r[0] not in nomes_novos]
    novas = []
    for nome, _ in ATER_INDIC:
        fonte = FONTE_ATER_RECEBE if nome == "% que recebe orientação técnica" else FONTE_ATER_ORIGEM
        novas.append([nome, "percentual", quantile_breaks(dist[nome]), fonte])
    novas.append([INTERNET_INDIC, "percentual", quantile_breaks(dist[INTERNET_INDIC]), FONTE_INTERNET])
    out_csv = os.path.join(DIR, "indicadores.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
        w.writerows(novas)
    print(f"  indicadores.csv: {len(body)} linhas antigas + {len(novas)} novas -> {out_csv}")

    # ---------- UF: objeto JS ----------
    ater_uf = {r["ibge2"]: r for r in read_csv("ater_orientacao_uf.csv")}
    net_uf = {r["ibge2"]: r for r in read_csv("internet_uf.csv")}
    uf_pct = {}  # nome -> {sigla: ratio}
    for nome, col in ATER_INDIC:
        uf_pct[nome] = {}
        for ibge2, r in ater_uf.items():
            v = ratio(num(r[col]), num(r["total"]))
            if v is not None:
                uf_pct[nome][UF_SIGLA[ibge2]] = round(v, 4)
    uf_pct[INTERNET_INDIC] = {}
    for ibge2, r in net_uf.items():
        v = ratio(num(r["domicilios_com_internet"]), num(r["domicilios_total"]))
        if v is not None:
            uf_pct[INTERNET_INDIC][UF_SIGLA[ibge2]] = round(v, 4)

    snippet = "var UF_PCT = " + json.dumps(uf_pct, ensure_ascii=False, indent=0).replace("\n", "") + ";\n"
    out_js = os.path.join(DIR, "UF_PCT_snippet.js")
    with open(out_js, "w", encoding="utf-8") as f:
        f.write(snippet)
    print(f"  UF_PCT -> {out_js} ({len(uf_pct)} indicadores x {len(UF_SIGLA)} UFs)")

    # validação
    r = uf_pct["% que recebe orientação técnica"]
    net = uf_pct[INTERNET_INDIC]
    print("\nAmostra UF (% recebe orientação | % internet):")
    for s in ["SP", "BA", "RS", "PA", "MA"]:
        print(f"  {s}: {r.get(s,0)*100:.1f}%  |  {net.get(s,0)*100:.1f}%")
    print("\nNOVOS INDICADORES (nomes p/ SELECTOR):")
    for nome, _ in ATER_INDIC:
        print("  -", nome)
    print("  -", INTERNET_INDIC)


if __name__ == "__main__":
    main()
