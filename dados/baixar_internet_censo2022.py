#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baixar_internet_censo2022.py
----------------------------
Baixa do SIDRA (tabela 9936, Censo Demográfico 2022) o número de domicílios
particulares permanentes ocupados por existência de conexão domiciliar à internet,
por município e por UF. Deriva o indicador:

  % de domicílios com acesso à internet = Sim / Total

Variável 381 (Domicílios particulares permanentes ocupados). Classificação C2072
"Existência de conexão domiciliar à Internet": Total=77584, Sim=77585. Demais
classificações (C63 condição de ocupação, C125 tipo de domicílio) na categoria
Total. Denominador = domicílios particulares permanentes ocupados (Total).

Gera em `dados/`:
  - internet_municipio.csv  (ibge7, municipio, uf, domicilios_total, domicilios_com_internet)
  - internet_uf.csv         (ibge2, uf, estado, domicilios_total, domicilios_com_internet)

Valores especiais do SIDRA viram vazio (não inventar). Uso:
    python3 baixar_internet_censo2022.py
"""
import csv, json, os, time, urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))

UF_CODES = ["11","12","13","14","15","16","17","21","22","23","24","25","26","27",
            "28","29","31","32","33","35","41","42","43","50","51","52","53"]
UF_SIGLA = {"11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO",
            "21":"MA","22":"PI","23":"CE","24":"RN","25":"PB","26":"PE","27":"AL",
            "28":"SE","29":"BA","31":"MG","32":"ES","33":"RJ","35":"SP","41":"PR",
            "42":"SC","43":"RS","50":"MS","51":"MT","52":"GO","53":"DF"}

BASE = ("https://apisidra.ibge.gov.br/values/t/9936/{nivel}/v/381/p/2022/"
        "C2072/77584,77585/C63/95826/C125/2932")


def fetch(nivel):
    url = BASE.format(nivel=nivel)
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  ...falha ({e}); tentando de novo")
            time.sleep(3)
    raise RuntimeError(f"SIDRA não respondeu para {nivel}")


def valor(v):
    v = (v or "").strip()
    if v in ("", "-", "..", "...", "X", "x"):
        return None
    try:
        return int(round(float(v.replace(",", "."))))
    except ValueError:
        return None


def registros(data):
    """cod IBGE (D1C) -> {'nome','total','sim'} usando C2072 (D4C)."""
    regs = {}
    for row in data[1:]:
        cod = row["D1C"]
        reg = regs.setdefault(cod, {"nome": row["D1N"]})
        if row["D4C"] == "77584":
            reg["total"] = valor(row["V"])
        elif row["D4C"] == "77585":
            reg["sim"] = valor(row["V"])
    return regs


def escreve(path, header_ids, regs, ordem):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header_ids + ["domicilios_total", "domicilios_com_internet"])
        for cod, extra, nome_fallback in ordem:
            r = regs.get(cod, {})
            nome = r.get("nome", nome_fallback)
            nome = nome.rsplit(" - ", 1)[0] if " - " in nome else nome
            tot = r.get("total"); sim = r.get("sim")
            w.writerow(extra + [nome, "" if tot is None else tot,
                                "" if sim is None else sim])


def main():
    print("Baixando UF (N3)…")
    regs_uf = registros(fetch("n3/all"))
    path_uf = os.path.join(DIR, "internet_uf.csv")
    with open(path_uf, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ibge2", "uf", "estado", "domicilios_total", "domicilios_com_internet"])
        for cod in UF_CODES:
            r = regs_uf.get(cod, {})
            nome = r.get("nome", "")
            tot = r.get("total"); sim = r.get("sim")
            w.writerow([cod, UF_SIGLA[cod], nome,
                        "" if tot is None else tot, "" if sim is None else sim])
    print(f"  -> {path_uf} ({len(UF_CODES)} UFs)")

    print("Baixando municípios (N6, por UF)…")
    path_mun = os.path.join(DIR, "internet_municipio.csv")
    total_mun = 0
    with open(path_mun, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ibge7", "municipio", "uf", "domicilios_total", "domicilios_com_internet"])
        for cod in UF_CODES:
            sigla = UF_SIGLA[cod]
            print(f"  {sigla}…", end="", flush=True)
            regs = registros(fetch(f"n6/in%20n3%20{cod}"))
            for ibge7 in sorted(regs):
                r = regs[ibge7]
                nome = r["nome"].rsplit(" - ", 1)[0]
                tot = r.get("total"); sim = r.get("sim")
                w.writerow([ibge7, nome, sigla,
                            "" if tot is None else tot, "" if sim is None else sim])
                total_mun += 1
            print(f" {len(regs)}")
            time.sleep(0.4)
    print(f"  -> {path_mun} ({total_mun} municípios)")

    tot = sum(int(regs_uf[c].get("total") or 0) for c in UF_CODES)
    sim = sum(int(regs_uf[c].get("sim") or 0) for c in UF_CODES)
    print(f"\nValidação (soma UF): domicílios={tot:,} | com internet={sim:,} | "
          f"%={100*sim/tot:.1f}%")


if __name__ == "__main__":
    main()
