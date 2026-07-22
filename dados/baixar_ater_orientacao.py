#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baixar_ater_orientacao.py
-------------------------
Baixa do SIDRA (tabela 6881, Censo Agropecuário 2017) o número de estabelecimentos
agropecuários com área por ORIGEM DA ORIENTAÇÃO TÉCNICA recebida, por município e
por UF. Gera dois CSVs em `dados/`:

  - ater_orientacao_municipio.csv  (ibge7, municipio, uf, + contagens por categoria)
  - ater_orientacao_uf.csv         (ibge2, uf, estado, + contagens por categoria)

Variável 9587 (Número de estabelecimentos agropecuários com área). Classificação
C12567 "Origem da orientação técnica recebida". Nas demais classificações usamos
sempre a categoria Total (C829=46302, C222=110087, C218=46502, C12517=113601).

Um estabelecimento pode receber orientação de mais de uma origem, então a soma das
origens é maior que "Recebe" — os percentuais derivados não somam 100%.

Valores especiais do SIDRA ('-', '..', '...', 'X') viram vazio: dado ausente NÃO é
inventado (sigilo estatístico do IBGE). Municipal é baixado iterando por UF para
não estourar o limite de células (mesmo padrão de merge_estabelecimentos_munic.py).

Uso:  python3 baixar_ater_orientacao.py
"""
import csv, json, os, time, urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))

# Categorias da classificação C12567 (código SIDRA -> chave/coluna no CSV)
CATS = [
    ("41151",  "total"),
    ("113111", "recebe"),
    ("112647", "governo"),
    ("112648", "propria"),
    ("112649", "cooperativas"),
    ("112650", "integradoras"),
    ("112651", "privadas"),
    ("112652", "ong"),
    ("45932",  "sistema_s"),
    ("112653", "outra"),
    ("113559", "nao_recebe"),
]
COD2KEY = {c: k for c, k in CATS}
COLS = [k for _, k in CATS]

UF_CODES = ["11","12","13","14","15","16","17","21","22","23","24","25","26","27",
            "28","29","31","32","33","35","41","42","43","50","51","52","53"]
UF_SIGLA = {"11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO",
            "21":"MA","22":"PI","23":"CE","24":"RN","25":"PB","26":"PE","27":"AL",
            "28":"SE","29":"BA","31":"MG","32":"ES","33":"RJ","35":"SP","41":"PR",
            "42":"SC","43":"RS","50":"MS","51":"MT","52":"GO","53":"DF"}

BASE = ("https://apisidra.ibge.gov.br/values/t/6881/{nivel}/v/9587/p/2017/"
        "C829/46302/C222/110087/C218/46502/C12517/113601/C12567/all")


def fetch(nivel):
    url = BASE.format(nivel=nivel)
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  ...falha ({e}); tentando de novo")
            time.sleep(3)
    raise RuntimeError(f"SIDRA não respondeu para {nivel}")


def valor(v):
    """String do SIDRA -> int, ou None se ausente/suprimido.

    Semântica do SIDRA: '-' é ZERO ABSOLUTO (não resultante de arredondamento);
    'X' é sigilo estatístico; '..'/'...' são não-aplicável/não-disponível.
    Só X/../... viram None — zero é dado real e entra como 0.
    """
    v = (v or "").strip()
    if v == "-":
        return 0
    if v in ("", "..", "...", "X", "x"):
        return None
    try:
        return int(round(float(v.replace(",", "."))))
    except ValueError:
        return None


def linhas_para_registros(data, cod_dim):
    """Agrupa as linhas do SIDRA por unidade territorial (cod_dim = 'D1C')."""
    regs = {}
    nome_dim = "D1N"
    for row in data[1:]:
        cod = row[cod_dim]
        reg = regs.setdefault(cod, {"nome": row[nome_dim]})
        catcod = row["D8C"]
        key = COD2KEY.get(catcod)
        if key:
            reg[key] = valor(row["V"])
    return regs


def main():
    # ---- UF ----
    print("Baixando UF (N3)…")
    data_uf = fetch("n3/all")
    regs_uf = linhas_para_registros(data_uf, "D1C")
    path_uf = os.path.join(DIR, "ater_orientacao_uf.csv")
    with open(path_uf, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ibge2", "uf", "estado"] + COLS)
        for cod in UF_CODES:
            r = regs_uf.get(cod, {})
            estado = r.get("nome", "")
            w.writerow([cod, UF_SIGLA[cod], estado] +
                       ["" if r.get(k) is None else r.get(k) for k in COLS])
    print(f"  -> {path_uf} ({len(UF_CODES)} UFs)")

    # ---- Municípios (iterando por UF) ----
    print("Baixando municípios (N6, por UF)…")
    path_mun = os.path.join(DIR, "ater_orientacao_municipio.csv")
    total_mun = 0
    with open(path_mun, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ibge7", "municipio", "uf"] + COLS)
        for cod in UF_CODES:
            sigla = UF_SIGLA[cod]
            print(f"  {sigla}…", end="", flush=True)
            data = fetch(f"n6/in%20n3%20{cod}")
            regs = linhas_para_registros(data, "D1C")
            for ibge7 in sorted(regs):
                r = regs[ibge7]
                nome = r["nome"].rsplit(" - ", 1)[0]  # "Adamantina - SP" -> "Adamantina"
                w.writerow([ibge7, nome, sigla] +
                           ["" if r.get(k) is None else r.get(k) for k in COLS])
                total_mun += 1
            print(f" {len(regs)}")
            time.sleep(0.5)
    print(f"  -> {path_mun} ({total_mun} municípios)")

    # ---- Validação rápida ----
    tot = sum(int(regs_uf[c].get("total") or 0) for c in UF_CODES)
    rec = sum(int(regs_uf[c].get("recebe") or 0) for c in UF_CODES)
    print(f"\nValidação (soma UF): total={tot:,} | recebe={rec:,} | "
          f"% recebe={100*rec/tot:.1f}%")


if __name__ == "__main__":
    main()
