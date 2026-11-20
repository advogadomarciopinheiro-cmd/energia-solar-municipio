#!/usr/bin/env python3
"""Roteiro noturno: publica UMA nova cidade da fila (data/processed/fila.json).

Idempotente: pula cidades já em data/processed/publicadas.json. Atualiza publicadas.json,
reconstrói o site e registra em data/processed/nightly_log.jsonl.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
TZ = ZoneInfo("America/Sao_Paulo")
LOG = PROC / "nightly_log.jsonl"


def main() -> int:
    mun = json.loads((PROC / "municipios.json").read_text(encoding="utf-8"))
    pub_file = PROC / "publicadas.json"
    pub = json.loads(pub_file.read_text(encoding="utf-8")) if pub_file.exists() else []
    fila = json.loads((PROC / "fila.json").read_text(encoding="utf-8"))
    feitos = {p["ibge"] for p in pub}
    pendentes = [i for i in fila if i not in feitos and i in mun]
    agora = datetime.now(TZ)
    entry = {"quando": agora.strftime("%d/%m/%Y %H:%M") + " (horário de Brasília, UTC-3)"}
    if not pendentes:
        entry.update(status="fila_vazia", titulo="", href="", restantes=0)
        print("Fila vazia: nenhuma cidade nova para publicar.")
    else:
        ib = pendentes[0]
        m = mun[ib]
        pub.append({"ibge": ib, "data": agora.strftime("%d/%m/%Y"), "origem": "noturno"})
        pub_file.write_text(json.dumps(pub, ensure_ascii=False, indent=1), encoding="utf-8")
        href = f"municipio/{m['slug']}/"
        entry.update(status="publicada", ibge=ib, titulo=f"Energia solar em {m['nome']} ({m['uf']})",
                     href=href, restantes=len(pendentes) - 1)
        print(f"Nova cidade: {m['nome']} ({m['uf']}) -> {href} | restam {len(pendentes) - 1}")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")], check=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
