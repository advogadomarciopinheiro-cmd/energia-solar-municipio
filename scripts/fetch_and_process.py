#!/usr/bin/env python3
"""Baixa (se faltar) e processa os dados oficiais usados pelo site.

Fontes (todas abertas):
- INPE/LABREN, Atlas Brasileiro de Energia Solar, 2ª ed. (2017): irradiação no plano inclinado
  (inclinação = latitude) nas sedes municipais, CSV.
- ANEEL, Tarifas homologadas das distribuidoras (B1 residencial convencional, TUSD + TE, sem tributos).
- ANEEL, Componentes tarifárias 2025 e 2026 (componente TUSD_FioB, base da transição da Lei 14.300/2022).
- ANEEL, Relação de empreendimentos de geração distribuída (MMGD) — parquet.
- IBGE, estimativas de população 2026 (agregado 6579, variável 9324).

Requer pandas + pyarrow (só aqui; build.py e nightly.py usam só a biblioteca padrão).
Uso: python3 scripts/fetch_and_process.py [--refresh]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
TZ = ZoneInfo("America/Sao_Paulo")

SRC = {
    "atlas_inclinado": "https://labren.ccst.inpe.br/projetos/atlas_2017/TILTED_LATITUDE_sedes-munic_(csv).zip",
    "atlas_pagina": "https://labren.ccst.inpe.br/atlas_2017.html",
    "tarifas": "https://dadosabertos.aneel.gov.br/dataset/5a583f3e-1646-4f67-bf0f-69db4203e89e/resource/fcf2906c-7c32-4b9b-a637-054e7a5234f4/download/tarifas-homologadas-distribuidoras-energia-eletrica.csv",
    "tarifas_pagina": "https://dadosabertos.aneel.gov.br/dataset/tarifas-distribuidoras-energia-eletrica",
    "componentes_2025": "https://dadosabertos.aneel.gov.br/dataset/613e6b74-1a4b-4c48-a231-096815e96bd5/resource/a4060165-3a0c-404f-926c-83901088b67c/download/componentes-tarifarias-2025.csv",
    "componentes_2026": "https://dadosabertos.aneel.gov.br/dataset/613e6b74-1a4b-4c48-a231-096815e96bd5/resource/e8717aa8-2521-453f-bf16-fbb9a16eea39/download/componentes-tarifarias-2026.csv",
    "componentes_pagina": "https://dadosabertos.aneel.gov.br/dataset/componentes-tarifarias",
    "gd": "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/resource/cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27/download/empreendimento-geracao-distribuida.parquet",
    "gd_pagina": "https://dadosabertos.aneel.gov.br/dataset/relacao-de-empreendimentos-de-geracao-distribuida",
    "ibge_pop": "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/2026/variaveis/9324?localidades=N6%5Ball%5D",
}
FILES = {
    "atlas_inclinado": RAW / "TILTED_LATITUDE_sedes.zip",
    "tarifas": RAW / "tarifas-homologadas.csv",
    "componentes_2025": RAW / "componentes-tarifarias-2025.csv",
    "componentes_2026": RAW / "componentes-tarifarias-2026.csv",
    "gd": RAW / "empreendimento-geracao-distribuida.parquet",
    "ibge_pop": RAW / "ibge_populacao_estimada_2026.json",
}
UF_NOME = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPÁ", "AM": "AMAZONAS", "BA": "BAHIA", "CE": "CEARÁ",
    "DF": "DISTRITO FEDERAL", "ES": "ESPÍRITO SANTO", "GO": "GOIÁS", "MA": "MARANHÃO", "MT": "MATO GROSSO",
    "MS": "MATO GROSSO DO SUL", "MG": "MINAS GERAIS", "PA": "PARÁ", "PB": "PARAÍBA", "PR": "PARANÁ",
    "PE": "PERNAMBUCO", "PI": "PIAUÍ", "RJ": "RIO DE JANEIRO", "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL", "RO": "RONDÔNIA", "RR": "RORAIMA", "SC": "SANTA CATARINA", "SP": "SÃO PAULO",
    "SE": "SERGIPE", "TO": "TOCANTINS",
}
POP_MIN = 100_000  # municípios candidatos ao diretório


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slugify(s: str) -> str:
    return norm(s).replace(" ", "-")


def now_br() -> str:
    return datetime.now(TZ).strftime("%d/%m/%Y %H:%M") + " (horário de Brasília, UTC-3)"


def download(key: str, refresh: bool) -> None:
    dest = FILES[key]
    if dest.exists() and not refresh:
        return
    print("baixando", SRC[key])
    subprocess.run(["curl", "-sSL", "-A", "Mozilla/5.0", "-m", "1200", "-o", str(dest), SRC[key]], check=True)


def load_pop() -> dict:
    d = json.loads(FILES["ibge_pop"].read_text(encoding="utf-8"))
    pop = {}
    for s in d[0]["resultados"][0]["series"]:
        loc = s["localidade"]
        nome, uf = loc["nome"].rsplit(" - ", 1)
        pop[loc["id"]] = {"nome": nome, "uf": uf, "populacao": int(s["serie"]["2026"])}
    return pop


def load_atlas() -> dict:
    with zipfile.ZipFile(FILES["atlas_inclinado"]) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as fh:
            df = pd.read_csv(fh, sep=";")
    out = {}
    anuais = sorted(int(x) for x in df.ANNUAL)
    import bisect
    for r in df.itertuples(index=False):
        out[(norm(r.NAME), r.STATE.upper())] = {
            "percentil_br": round(100 * bisect.bisect_left(anuais, int(r.ANNUAL)) / len(anuais)),
            "anual_wh_m2_dia": int(r.ANNUAL),
            "min_mensal_wh_m2_dia": int(min(r.JAN, r.FEB, r.MAR, r.APR, r.MAY, r.JUN, r.JUL, r.AUG, r.SEP, r.OCT, r.NOV, r.DEC)),
            "lat": float(r.LAT), "lon": float(r.LON), "celula_id": int(r.ID),
        }
    return out


def pick_vigente(df: pd.DataFrame, hoje: str) -> pd.DataFrame:
    df = df[(df.DatInicioVigencia <= hoje) & (df.DatFimVigencia >= hoje)]
    return df.sort_values("DatInicioVigencia").groupby("cnpj").tail(1)


def num(s: str) -> float:
    s = str(s).strip()
    if s.startswith(","):
        s = "0" + s
    return float(s.replace(".", "").replace(",", ".")) if "E" not in s.upper() else float(s.replace(",", "."))


def load_tarifas(hoje: str) -> dict:
    df = pd.read_csv(FILES["tarifas"], sep=";", dtype=str, encoding="utf-8")
    q = df[(df.DscBaseTarifaria == "Tarifa de Aplicação") & (df.DscSubGrupo == "B1")
           & (df.DscModalidadeTarifaria == "Convencional") & (df.DscClasse == "Residencial")
           & (df.DscSubClasse == "Residencial") & (df.DscDetalhe == "Não se aplica")].copy()
    q["cnpj"] = q.NumCNPJDistribuidora.str.zfill(14)
    v = pick_vigente(q, hoje)
    gerado = df.DatGeracaoConjuntoDados.max()
    out = {}
    for r in v.itertuples(index=False):
        tusd, te = num(r.VlrTUSD), num(r.VlrTE)
        out[r.cnpj] = {
            "sigla": r.SigAgente, "reh": r.DscREH, "inicio": r.DatInicioVigencia, "fim": r.DatFimVigencia,
            "tusd_mwh": round(tusd, 2), "te_mwh": round(te, 2), "total_kwh": round((tusd + te) / 1000, 5),
        }
    return out, gerado


def load_fiob() -> tuple[dict, str]:
    cols = ["SigNomeAgente", "NumCPFCNPJ", "DatInicioVigencia", "DatFimVigencia", "DscBaseTarifaria",
            "DscSubGrupoTarifario", "DscModalidadeTarifaria", "DscClasseConsumidor", "DscSubClasseConsumidor",
            "DscDetalheConsumidor", "DscComponenteTarifario", "VlrComponenteTarifario", "DatGeracaoConjuntoDados"]
    parts, gerado = [], ""
    for key in ("componentes_2025", "componentes_2026"):
        for chunk in pd.read_csv(FILES[key], sep=";", dtype=str, usecols=cols, chunksize=500_000):
            c = chunk[(chunk.DscComponenteTarifario == "TUSD_FioB") & (chunk.DscSubGrupoTarifario == "B1")
                      & (chunk.DscClasseConsumidor == "Residencial") & (chunk.DscSubClasseConsumidor == "Residencial")
                      & (chunk.DscModalidadeTarifaria == "Convencional") & (chunk.DscBaseTarifaria == "Tarifa de Aplicação")
                      & (chunk.DscDetalheConsumidor == "Não se aplica")]
            parts.append(c)
            gerado = max(gerado, chunk.DatGeracaoConjuntoDados.max())
    df = pd.concat(parts)
    df["cnpj"] = df.NumCPFCNPJ.str.zfill(14)
    out = {}
    for r in df.itertuples(index=False):
        out[(r.cnpj, r.DatInicioVigencia)] = round(num(r.VlrComponenteTarifario), 2)
    return out, gerado


def load_gd(ibges: set[int]) -> tuple[dict, dict]:
    cols = ["CodMunicipioIbge", "NumCNPJDistribuidora", "SigAgente", "NomAgente", "DscClasseConsumo",
            "DscFonteGeracao", "DscPorte", "MdaPotenciaInstaladaKW", "QtdUCRecebeCredito",
            "AnmPeriodoReferencia", "DatGeracaoConjuntoDados"]
    df = pd.read_parquet(FILES["gd"], columns=cols)
    meta = {"periodo": str(df.AnmPeriodoReferencia.max()), "gerado": str(df.DatGeracaoConjuntoDados.max()),
            "registros": int(len(df))}
    df = df[df.CodMunicipioIbge.isin(ibges)]
    solar = df[df.DscFonteGeracao == "Radiação solar"]
    out = {}
    for ib, g in df.groupby("CodMunicipioIbge"):
        s = solar[solar.CodMunicipioIbge == ib]
        res = s[s.DscClasseConsumo == "Residencial"]
        dist = (g.groupby(["NumCNPJDistribuidora", "SigAgente", "NomAgente"]).size()
                .sort_values(ascending=False).reset_index(name="n"))
        out[str(ib)] = {
            "solar_n": int(len(s)), "solar_kw": round(float(s.MdaPotenciaInstaladaKW.sum()), 1),
            "solar_micro_n": int((s.DscPorte == "Microgeracao").sum()),
            "solar_mini_n": int((s.DscPorte == "Minigeracao").sum()),
            "solar_res_n": int(len(res)), "solar_res_kw": round(float(res.MdaPotenciaInstaladaKW.sum()), 1),
            "solar_res_kw_medio": round(float(res.MdaPotenciaInstaladaKW.mean()), 2) if len(res) else None,
            "ucs_credito": int(s.QtdUCRecebeCredito.sum()),
            "distribuidoras": [
                {"cnpj": str(int(r.NumCNPJDistribuidora)).zfill(14), "sigla": r.SigAgente, "nome": r.NomAgente,
                 "n": int(r.n), "share": round(int(r.n) / len(g), 4)}
                for r in dist.itertuples(index=False)
            ],
        }
    return out, meta


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    refresh = "--refresh" in argv
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for k in FILES:
        if k == "ibge_pop" and not FILES[k].exists():
            subprocess.run(["curl", "-sSL", "-m", "300", "-o", str(FILES[k]), SRC[k]], check=True)
        elif k != "ibge_pop":
            download(k, refresh)

    hoje = date.today().isoformat()
    pop = load_pop()
    atlas = load_atlas()
    tarifas, tarifas_gerado = load_tarifas(hoje)
    fiob, comp_gerado = load_fiob()
    cand = {k: v for k, v in pop.items() if v["populacao"] >= POP_MIN}
    gd, gd_meta = load_gd({int(k) for k in cand})

    munis, sem = {}, []
    for ib, p in cand.items():
        a = atlas.get((norm(p["nome"]), UF_NOME[p["uf"]]))
        g = gd.get(ib)
        if not a or not g or not g["distribuidoras"]:
            sem.append(f"{p['nome']}-{p['uf']}: atlas={'ok' if a else 'não'} gd={'ok' if g else 'não'}")
            continue
        principal = g["distribuidoras"][0]
        t = tarifas.get(principal["cnpj"])
        if not t:
            sem.append(f"{p['nome']}-{p['uf']}: sem tarifa B1 vigente para {principal['sigla']}")
            continue
        fb = fiob.get((principal["cnpj"], t["inicio"]))
        munis[ib] = {
            "ibge": ib, "nome": p["nome"], "uf": p["uf"], "slug": f"{slugify(p['nome'])}-{p['uf'].lower()}",
            "populacao": p["populacao"], "atlas": a, "gd": g,
            "tarifa": dict(t, cnpj=principal["cnpj"], tusd_fiob_mwh=fb),
        }
    meta = {
        "processado_em": now_br(),
        "data_referencia": hoje,
        "fontes": {
            "atlas": {"arquivo": SRC["atlas_inclinado"], "pagina": SRC["atlas_pagina"],
                      "descricao": "Atlas Brasileiro de Energia Solar, 2ª ed. (INPE/LABREN, 2017) — irradiação no plano inclinado (inclinação igual à latitude), médias de 1999 a 2015, sedes municipais",
                      "baixado_em": "20/11/2026"},
            "tarifas": {"arquivo": SRC["tarifas"], "pagina": SRC["tarifas_pagina"], "gerado": tarifas_gerado},
            "componentes": {"arquivos": [SRC["componentes_2025"], SRC["componentes_2026"]], "pagina": SRC["componentes_pagina"], "gerado": comp_gerado},
            "gd": {"arquivo": SRC["gd"], "pagina": SRC["gd_pagina"], **gd_meta},
            "ibge": {"api": SRC["ibge_pop"], "periodo": "2026", "agregado": "6579", "variavel": "9324"},
        },
        "sem_dados": sem,
    }
    (OUT / "municipios.json").write_text(json.dumps(munis, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(munis)} municípios processados; {len(sem)} sem dados completos")
    for s in sem:
        print("  -", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
