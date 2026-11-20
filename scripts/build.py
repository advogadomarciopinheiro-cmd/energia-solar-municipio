#!/usr/bin/env python3
"""Gera o site estático em ./site a partir de data/processed (só biblioteca padrão)."""
from __future__ import annotations

import html
import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "site"
TZ = ZoneInfo("America/Sao_Paulo")

REPO = "energia-solar-municipio"
BASE = os.environ.get("BASE_URL", f"/{REPO}/")
SITE_URL = os.environ.get("SITE_URL", f"https://advogadomarciopinheiro-cmd.github.io/{REPO}").rstrip("/")

SITE_NOME = "Energia Solar no Município"
EMPRESA = "MM Consultoria Corporativa Ltda."
CNPJ = "49.399.582/0001-10"
EMAIL = "solucoescorporativasmm@gmail.com"

# Parceiros/afiliados. Lista vazia = seção oculta. Quando preenchida, aparece com o rótulo
# "Publicidade" (CONAR) e links rel="sponsored". Formato:
# {"nome": "...", "url": "https://...", "texto": "...", "ufs": ["CE", "BA"]}  (ufs vazio = todas)
PARCEIROS: list[dict] = []

# ---------------- premissas da estimativa (todas citadas na metodologia) ----------------
PR_MIN, PR_MAX = 0.70, 0.80  # taxa de desempenho, Manual de Engenharia FV CEPEL/CRESESB (2014), seção 6.4.1
CUSTO_KWP_MIN, CUSTO_KWP_MAX = 2910.0, 3620.0  # R$/kWp, Greener jun/2026 (4 kWp e 2 kWp), via pv magazine 25/09/2026
FIOB_PCT = {2026: 0.60, 2027: 0.75, 2028: 0.90}  # Lei 14.300/2022, art. 27
FIOB_POS_2028 = 1.00  # premissa conservadora para 2029+ (regra do art. 17 ainda a definir pela ANEEL)
ANO_INICIO = 2027  # sistema contratado agora entra em operação, em regra, no ano que vem

FONTES = {
    "atlas": ("Atlas Brasileiro de Energia Solar, 2ª ed. — INPE/LABREN (2017)", "https://labren.ccst.inpe.br/atlas_2017.html"),
    "tarifas": ("ANEEL — Tarifas homologadas das distribuidoras (dados abertos)", "https://dadosabertos.aneel.gov.br/dataset/tarifas-distribuidoras-energia-eletrica"),
    "componentes": ("ANEEL — Componentes tarifárias (dados abertos)", "https://dadosabertos.aneel.gov.br/dataset/componentes-tarifarias"),
    "gd": ("ANEEL — Relação de empreendimentos de geração distribuída (dados abertos)", "https://dadosabertos.aneel.gov.br/dataset/relacao-de-empreendimentos-de-geracao-distribuida"),
    "ibge": ("IBGE — Estimativas da população 2026 (SIDRA, tabela 6579)", "https://sidra.ibge.gov.br/tabela/6579"),
    "lei": ("Lei nº 14.300, de 6 de janeiro de 2022 (Planalto)", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14300.htm"),
    "cepel": ("CEPEL/CRESESB — Manual de Engenharia para Sistemas Fotovoltaicos (2014), seção 6.4.1", "https://cresesb.cepel.br/publicacoes/download/Manual_de_Engenharia_FV_2014.pdf"),
    "greener": ("Greener, estudo Soluções Energéticas Distribuídas, 1º sem. 2026, publicado pela pv magazine Brasil em 25/09/2026", "https://www.pv-magazine-brasil.com/2026/09/25/sistemas-fotovoltaicos-ficam-ate-7-mais-caros-no-1o-semestre-de-2026-aponta-greener/"),
}

e = html.escape


def load(name):
    return json.loads((PROC / name).read_text(encoding="utf-8"))


META = load("meta.json")
MUN = load("municipios.json")
PUB_FILE = PROC / "publicadas.json"


def load_pub() -> list[dict]:
    return json.loads(PUB_FILE.read_text(encoding="utf-8")) if PUB_FILE.exists() else []


def hoje():
    return datetime.now(TZ).strftime("%d/%m/%Y")


def br_date(iso: str) -> str:
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def fint(n) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


def fnum(x, d=2) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(x, d=2) -> str:
    return "R$ " + fnum(x, d)


def nome_dist(n: str) -> str:
    small = {"de", "do", "da", "dos", "das", "e"}
    ws = [w.capitalize() if w.lower() not in small else w.lower() for w in n.split()]
    return " ".join(w.upper() if w.upper() in {"S.A.", "S.A", "SA", "S/A", "CEB", "EDP", "CPFL", "RGE", "CEEE"} else w for w in ws)


def url(path=""):
    return BASE + path.lstrip("/")


def abs_url(path=""):
    return SITE_URL + "/" + path.lstrip("/")


def fonte(key, extra=""):
    n, u = FONTES[key]
    return f'<a href="{e(u)}" rel="noopener" target="_blank">{e(n)}</a>{extra}'


# ---------------- cálculo ----------------
def calc(m: dict) -> dict:
    H = m["atlas"]["anual_wh_m2_dia"] / 1000  # kWh/m².dia = horas de sol pleno
    t = m["tarifa"]
    T = t["total_kwh"]
    fiob = (t.get("tusd_fiob_mwh") or 0) / 1000
    def valor(ano):
        pct = FIOB_PCT.get(ano, FIOB_POS_2028 if ano > 2028 else 0)
        return T - pct * fiob
    def payback(pr, custo):
        gen = H * 365 * pr
        acum, ano = 0.0, ANO_INICIO
        for i in range(1, 41):
            acum += gen * valor(ano)
            if acum >= custo:
                falta = acum - custo
                return i - falta / (gen * valor(ano))
            ano += 1
        return None
    r = {
        "H": H, "T": T, "fiob": fiob,
        "gen_mes_min": H * 365 / 12 * PR_MIN, "gen_mes_max": H * 365 / 12 * PR_MAX,
        "gen_ano_min": H * 365 * PR_MIN, "gen_ano_max": H * 365 * PR_MAX,
        "valor": {a: valor(a) for a in (2027, 2028, 2029)},
        "pb_otimista": payback(PR_MAX, CUSTO_KWP_MIN),
        "pb_conservador": payback(PR_MIN, CUSTO_KWP_MAX),
    }
    r["eco_ano1_min"] = r["gen_ano_min"] * r["valor"][ANO_INICIO]
    r["eco_ano1_max"] = r["gen_ano_max"] * r["valor"][ANO_INICIO]
    # exemplo: gerar 300 kWh/mês
    r["kwp_300_min"] = 300 / r["gen_mes_max"]
    r["kwp_300_max"] = 300 / r["gen_mes_min"]
    return r


# ---------------- e-mail de orçamento ----------------
def mailto(cidade_uf: str = "", distribuidora: str = "") -> str:
    assunto = f"Orçamento solar — {cidade_uf}" if cidade_uf else "Orçamento solar — (sua cidade/UF)"
    corpo = (
        "Olá, quero receber orçamentos de energia solar para a minha casa.\n\n"
        f"Cidade/UF: {cidade_uf}\n"
        "Bairro (opcional):\n"
        f"Distribuidora: {distribuidora}\n"
        "Consumo médio mensal em kWh (está na conta de luz):\n"
        "Tipo de ligação (monofásica, bifásica ou trifásica), se souber:\n"
        "Tipo de telhado (cerâmico, fibrocimento, metálico, laje):\n"
        "Imóvel próprio? (sim/não):\n"
        "Melhor forma de contato além deste e-mail (opcional):\n\n"
        "Não envie documentos, CPF, senhas nem foto da conta nesta primeira mensagem.\n\n"
        f"CONSENTIMENTO (obrigatório): autorizo a {EMPRESA} (CNPJ {CNPJ}) a usar meu nome, meu e-mail "
        "e as informações deste e-mail para responder ao meu pedido de orçamento por este canal. "
        "Posso revogar a qualquer momento respondendo REVOGAR.\n\n"
        "COMPARTILHAMENTO (opcional, consentimento separado): escreva SIM se autoriza o envio destas informações "
        "a até 3 empresas instaladoras para que elas me mandem orçamentos: ___\n"
    )
    return f"mailto:{EMAIL}?subject={quote(assunto)}&body={quote(corpo)}"


# ---------------- layout ----------------
CSS = """
:root{--bg:#f7f8f4;--card:#fff;--ink:#1f2a1f;--muted:#5c665a;--brand:#9a5b00;--brand2:#fff3dc;--sun:#f2a900;--warn:#fff5e0;--warnb:#e0a100;--line:#e4e6df;--ok:#1f6f43}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);background:var(--bg)}
a{color:var(--brand)}a:hover{text-decoration:none}
.skip{position:absolute;left:-999px}.skip:focus{left:8px;top:8px;background:#fff;padding:6px;z-index:9}
.wrap{max-width:980px;margin:0 auto;padding:0 16px}
header.top{background:#fff;border-bottom:3px solid var(--sun)}
header.top .wrap{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;padding-top:12px;padding-bottom:12px}
.logo{font-weight:700;color:var(--ink);text-decoration:none;font-size:1.08rem}.logo span{color:var(--brand)}
nav a{margin-right:14px;text-decoration:none;color:var(--muted);font-size:.95rem}nav a.cta{color:#fff;background:var(--brand);padding:6px 12px;border-radius:6px;margin-right:0}
main{padding:24px 0 40px}
h1{font-size:1.7rem;line-height:1.25;margin:.2em 0 .5em}h2{font-size:1.25rem;margin:1.7em 0 .5em}h3{font-size:1.05rem}
.lead{font-size:1.1rem;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:14px 0}
.grid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:640px){.grid{grid-template-columns:1fr 1fr}h1{font-size:2rem}}
@media(min-width:900px){.grid.g4{grid-template-columns:repeat(4,1fr)}.grid.g3{grid-template-columns:repeat(3,1fr)}}
.grid a.card{display:block;text-decoration:none;color:var(--ink);margin:0}.grid a.card:hover{border-color:var(--brand)}
.kpi{margin:0}.kpi .v{font-size:1.35rem;font-weight:700;display:block}.kpi .l{font-size:.85rem;color:var(--muted)}
.tag{display:inline-block;font-size:.78rem;background:var(--brand2);color:var(--brand);padding:2px 8px;border-radius:99px;margin-bottom:6px}
.alert{background:var(--warn);border-left:4px solid var(--warnb);padding:12px 16px;border-radius:6px;margin:16px 0}
.answer{background:#fff;border:1px solid var(--line);border-left:5px solid var(--sun);border-radius:8px;padding:14px 18px;margin:16px 0}
.cta-box{background:#3b2a00;color:#fff;border-radius:10px;padding:18px 20px;margin:28px 0}.cta-box a.btn{background:var(--sun);color:#1f1a00}
.cta-box p{margin:.4em 0}.cta-box a{color:#ffe1a0}
a.btn{display:inline-block;background:var(--brand);color:#fff;text-decoration:none;padding:10px 16px;border-radius:8px;font-weight:600;margin-top:8px}
.small{font-size:.88rem;color:var(--muted)}.cta-box .small{color:#f1e3c2}
table{width:100%;border-collapse:collapse;font-size:.95rem;background:#fff}td,th{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}
th{font-weight:600}
.tbl{overflow-x:auto}
.crumbs{font-size:.85rem;color:var(--muted)}.crumbs a{color:var(--muted)}
ul.src li{margin:.3em 0}
.ad-slot{border:1px dashed #c9b98f;border-radius:8px;padding:12px 16px;margin:24px 0;background:#fff}
.ad-slot .label{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
input[type=search]{width:100%;font:inherit;padding:10px 12px;border:1px solid #cfd3c8;border-radius:8px}
.muted{color:var(--muted)}
footer{border-top:1px solid var(--line);background:#fff;padding:20px 0;font-size:.88rem;color:var(--muted)}
footer a{color:var(--muted);margin-right:12px}
"""

JS = """
(function(){var q=document.getElementById('busca');if(!q)return;var items=[].slice.call(document.querySelectorAll('[data-busca]'));
var none=document.getElementById('sem-resultado');
function n(s){return (s||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();}
q.addEventListener('input',function(){var v=n(q.value.trim()),c=0;items.forEach(function(el){var ok=!v||n(el.getAttribute('data-busca')).indexOf(v)>=0;el.style.display=ok?'':'none';if(ok)c++;});if(none)none.style.display=c?'none':'';});})();
"""


def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + "</script>"


def page(path, title, desc, body, crumbs=None, extra_ld=None, script=False):
    canon = abs_url(path) if path != "404.html" else abs_url("")
    crumbs_html = ""
    lds = list(extra_ld or [])
    if crumbs:
        crumbs_html = '<div class="crumbs">' + " › ".join(
            f'<a href="{url(p)}">{e(n)}</a>' if p is not None else e(n) for n, p in crumbs) + "</div>"
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, **({"item": abs_url(p)} if p is not None else {})}
            for i, (n, p) in enumerate(crumbs)]})
    robots = '<meta name="robots" content="noindex">' if path == "404.html" else ""
    doc = f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">{robots}
<link rel="canonical" href="{e(canon)}">
<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(canon)}"><meta property="og:locale" content="pt_BR">
<link rel="stylesheet" href="{url('assets/style.css')}">
{''.join(ld(x) for x in lds)}
</head><body>
<a class="skip" href="#conteudo">Ir para o conteúdo</a>
<header class="top"><div class="wrap">
<a class="logo" href="{url()}">☀ Energia Solar <span>no Município</span></a>
<nav aria-label="Principal"><a href="{url('cidades/')}">Cidades</a><a href="{url('lei-14300/')}">Lei 14.300</a><a href="{url('metodologia/')}">Metodologia</a><a class="cta" href="{url('orcamentos/')}">Peça orçamentos</a></nav>
</div></header>
<main id="conteudo"><div class="wrap">{crumbs_html}
{body}
</div></main>
<footer><div class="wrap">
<p><strong>{EMPRESA}</strong> · CNPJ {CNPJ} · Consultoria empresarial. Contato somente por e-mail: <a href="mailto:{EMAIL}">{EMAIL}</a>. Este site não é a ANEEL, o INPE, o IBGE nem uma distribuidora de energia, e não instala sistemas solares. As estimativas são ilustrativas e não garantem economia.</p>
<p><a href="{url('cidades/')}">Cidades</a><a href="{url('metodologia/')}">Metodologia e fontes</a><a href="{url('lei-14300/')}">Lei 14.300</a><a href="{url('orcamentos/')}">Peça orçamentos</a><a href="{url('aviso-legal/')}">Aviso legal</a><a href="{url('privacidade/')}">Privacidade</a></p>
<p>Este site não usa cookies nem ferramentas de rastreamento.</p>
</div></footer>
{f'<script src="{url("assets/app.js")}"></script>' if script else ''}
</body></html>"""
    dest = OUT / path if path.endswith(".html") else OUT / path / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(doc, encoding="utf-8")


def parceiros_html(uf=None):
    itens = [p for p in PARCEIROS if not p.get("ufs") or uf in p.get("ufs", [])]
    if not itens:
        return "<!-- espaço de parceiros (Publicidade) vazio: PARCEIROS = [] -->"
    lis = "".join(f'<li><a href="{e(p["url"])}" rel="sponsored noopener" target="_blank">{e(p["nome"])}</a> — {e(p["texto"])}</li>' for p in itens)
    return (f'<aside class="ad-slot" aria-label="Publicidade"><div class="label">Publicidade</div><ul>{lis}</ul>'
            '<p class="small">Podemos receber comissão se você contratar por estes links. Isso não muda os dados nem as estimativas das páginas.</p></aside>')


def cta_box(cidade_uf="", distribuidora=""):
    return f"""<section class="cta-box" id="orcamento"><p><strong>Peça orçamentos{(' em ' + e(cidade_uf)) if cidade_uf else ''}</strong></p>
<p>Por enquanto o pedido é feito só por e-mail. O botão abre seu programa de e-mail com o assunto <em>“{e('Orçamento solar — ' + (cidade_uf or '<sua cidade>'))}”</em> e um roteiro com o que precisamos saber (consumo em kWh, tipo de telhado). Pedir orçamento por este canal não tem custo e não obriga você a contratar nada.</p>
<a class="btn" href="{e(mailto(cidade_uf, distribuidora))}">Pedir orçamento por e-mail</a>
<p class="small">Ao enviar o e-mail com o texto de consentimento, você autoriza a {EMPRESA} a usar seus dados só para responder ao pedido. Repassar seus dados a empresas instaladoras depende de um segundo consentimento, separado e opcional (escrever SIM no campo indicado). Detalhes na <a href="{url('privacidade/')}">política de privacidade</a>. A {EMPRESA} não instala sistemas e não garante preço, prazo ou economia de terceiros.</p></section>"""


def lei_resumo():
    return f"""<div class="tbl"><table>
<tr><th>Quando o pedido de conexão foi protocolado</th><th>Parcela do “Fio B” paga sobre a energia compensada</th></tr>
<tr><td>Até 12 meses após a publicação da lei (sistemas existentes ou protocolados até o início de janeiro de 2023)</td><td>0% até 31/12/2045 (regra antiga, art. 26)</td></tr>
<tr><td>Depois disso, faturamento em 2026</td><td>60%</td></tr>
<tr><td>Faturamento em 2027</td><td>75%</td></tr>
<tr><td>Faturamento em 2028</td><td>90%</td></tr>
<tr><td>A partir de 2029</td><td>Regra definitiva do art. 17, a ser fixada pela ANEEL com diretrizes do CNPE. Nesta estimativa, usamos 100% por prudência.</td></tr>
</table></div>
<p class="small">Fonte: {fonte('lei')}, arts. 26 e 27. Os percentuais incidem sobre as componentes tarifárias de remuneração dos ativos, depreciação e operação e manutenção da distribuição (o “Fio B”), e não sobre a tarifa inteira.</p>"""


def fontes_cidade(m):
    f = META["fontes"]
    return f"""<ul class="src small">
<li>Irradiação: {fonte('atlas')}, irradiação no plano inclinado na latitude, sede municipal (célula de 0,1° × 0,1°), médias de 1999 a 2015. Arquivo baixado em {f['atlas']['baixado_em']}. Fonte citada como: LABREN/CCST/INPE – Brasil.</li>
<li>Tarifa: {fonte('tarifas')}, conjunto gerado em {br_date(f['tarifas']['gerado'])}; {e(m['tarifa']['reh'].capitalize())}.</li>
<li>Fio B: {fonte('componentes')}, componente TUSD_FioB, conjunto gerado em {br_date(f['componentes']['gerado'])}.</li>
<li>Geração distribuída: {fonte('gd')}, referência {e(f['gd']['periodo'])}, conjunto gerado em {br_date(f['gd']['gerado'])}.</li>
<li>População: {fonte('ibge')}, estimativa 2026; código IBGE {e(m['ibge'])}.</li>
<li>Premissas: {fonte('cepel')}; {fonte('greener')}; {fonte('lei')}.</li>
</ul>"""


def city_page(m, data_pub):
    c = calc(m)
    t, g, a = m["tarifa"], m["gd"], m["atlas"]
    nome_uf = f"{m['nome']} ({m['uf']})"
    cidade_uf = f"{m['nome']}/{m['uf']}"
    princ = g["distribuidoras"][0]
    outras = [d for d in g["distribuidoras"][1:] if d["share"] >= 0.05]
    dist_txt = e(nome_dist(princ["nome"])) + f" ({e(t['sigla'])})"
    vig_aviso = ""
    if t["fim"] < date.today().isoformat():
        vig_aviso = f'<div class="alert">A tarifa abaixo teve vigência até {br_date(t["fim"])}. A distribuidora pode já ter tido reajuste; confira na ANEEL.</div>'
    outras_txt = ""
    if outras:
        outras_txt = "<p>O município também tem registros de geração distribuída em outra(s) distribuidora(s): " + ", ".join(
            f"{e(d['sigla'])} ({fnum(d['share']*100,0)}% dos registros)" for d in outras) + ". A tarifa exibida é a da principal.</p>"
    por_mil = g["solar_n"] / m["populacao"] * 1000
    pb1, pb2 = c["pb_otimista"], c["pb_conservador"]
    pb_txt = f"entre {fnum(pb1,1)} e {fnum(pb2,1)} anos" if pb1 and pb2 else "acima de 40 anos"
    resposta = (
        f"Pelos dados oficiais, cada 1 kWp de painéis em {e(m['nome'])} tende a gerar de <strong>{fint(c['gen_mes_min'])} a {fint(c['gen_mes_max'])} kWh por mês</strong>, "
        f"na média do ano. Com a tarifa residencial da {e(t['sigla'])} ({brl(c['T'],3)}/kWh sem impostos) e as regras de transição da Lei 14.300, "
        f"o investimento se pagaria, na nossa estimativa, <strong>{pb_txt}</strong>. "
        f"É uma estimativa com premissas públicas e conservadoras, não uma promessa: sombra, telhado, consumo e o preço do seu orçamento mudam o resultado."
    )
    body = f"""
<span class="tag">Código IBGE {e(m['ibge'])}</span>
<h1>Vale a pena energia solar em {e(nome_uf)}?</h1>
<div class="answer"><p>{resposta}</p></div>
<div class="grid g4">
<div class="card kpi"><span class="v">{fnum(c['H'],2)}</span><span class="l">kWh/m² por dia de sol no painel inclinado (média anual)</span></div>
<div class="card kpi"><span class="v">{brl(c['T'],3)}</span><span class="l">por kWh, tarifa B1 residencial {e(t['sigla'])}, sem tributos</span></div>
<div class="card kpi"><span class="v">{fint(g['solar_n'])}</span><span class="l">sistemas solares conectados (micro e minigeração)</span></div>
<div class="card kpi"><span class="v">{fint(m['populacao'])}</span><span class="l">habitantes (IBGE, estimativa 2026)</span></div>
</div>

<h2>Quanto sol {e(m['nome'])} recebe</h2>
<p>Na sede do município, a irradiação média sobre um painel voltado para o norte e inclinado na latitude local é de <strong>{fnum(c['H'],2)} kWh/m² por dia</strong> (média de 1999 a 2015). Isso fica acima de {a['percentil_br']}% das sedes municipais do Brasil no mesmo Atlas. No mês menos ensolarado, a média cai para {fnum(a['min_mensal_wh_m2_dia']/1000,2)} kWh/m² por dia.</p>
<p class="small">Fonte: Atlas Brasileiro de Energia Solar, 2ª ed., INPE/LABREN. O valor é da célula de cerca de 10 km × 10 km que contém a sede; bairros e telhados específicos podem variar.</p>

<h2>Distribuidora e tarifa</h2>
{vig_aviso}
<p>A distribuidora com {fnum(princ['share']*100,0) if princ['share'] < 0.995 else 'praticamente 100'}{'%' if princ['share'] < 0.995 else '%'} dos registros de geração distribuída no município é a <strong>{dist_txt}</strong>.</p>
{outras_txt}
<div class="tbl"><table>
<tr><th>Tarifa residencial B1, modalidade convencional</th><th>Valor</th></tr>
<tr><td>TUSD (uso do sistema de distribuição)</td><td>{brl(t['tusd_mwh']/1000,5)}/kWh</td></tr>
<tr><td>TE (energia)</td><td>{brl(t['te_mwh']/1000,5)}/kWh</td></tr>
<tr><td><strong>Total, sem ICMS, PIS/Cofins, iluminação pública e bandeira</strong></td><td><strong>{brl(c['T'],5)}/kWh</strong></td></tr>
<tr><td>Dentro da TUSD: componente “Fio B”, base da transição da Lei 14.300</td><td>{brl(c['fiob'],5)}/kWh</td></tr>
<tr><td>Vigência</td><td>{br_date(t['inicio'])} a {br_date(t['fim'])}</td></tr>
</table></div>
<p class="small">{e(t['reh'].capitalize())}. A conta de luz real é maior, porque inclui tributos, bandeira tarifária e a contribuição de iluminação pública. Usamos a tarifa sem tributos, o que deixa a estimativa de economia mais conservadora.</p>

<h2>Energia solar já instalada em {e(m['nome'])}</h2>
<div class="tbl"><table>
<tr><td>Sistemas solares de micro e minigeração distribuída</td><td><strong>{fint(g['solar_n'])}</strong> ({fint(g['solar_micro_n'])} micro e {fint(g['solar_mini_n'])} mini)</td></tr>
<tr><td>Potência solar instalada</td><td>{fnum(g['solar_kw']/1000,1)} MW</td></tr>
<tr><td>Sistemas em unidades residenciais</td><td>{fint(g['solar_res_n'])}, somando {fnum(g['solar_res_kw']/1000,1)} MW</td></tr>
<tr><td>Potência média dos sistemas residenciais</td><td>{fnum(g['solar_res_kw_medio'] or 0,2)} kW</td></tr>
<tr><td>Sistemas por mil habitantes</td><td>{fnum(por_mil,1)}</td></tr>
<tr><td>Unidades consumidoras que recebem créditos desses sistemas</td><td>{fint(g['ucs_credito'])}</td></tr>
</table></div>
<p class="small">Fonte: ANEEL, relação de empreendimentos de geração distribuída, referência {e(META['fontes']['gd']['periodo'])}. Conta os empreendimentos com fonte “Radiação solar” registrados com o código IBGE do município.</p>

<h2>Estimativa de geração, economia e retorno</h2>
<div class="tbl"><table>
<tr><th>Por 1 kWp instalado</th><th>Faixa estimada</th></tr>
<tr><td>Geração média mensal</td><td>{fint(c['gen_mes_min'])} a {fint(c['gen_mes_max'])} kWh</td></tr>
<tr><td>Geração anual</td><td>{fint(c['gen_ano_min'])} a {fint(c['gen_ano_max'])} kWh</td></tr>
<tr><td>Valor de cada kWh compensado em {ANO_INICIO} (tarifa menos 75% do Fio B)</td><td>{brl(c['valor'][2027],3)}</td></tr>
<tr><td>Valor de cada kWh compensado em 2028 (menos 90% do Fio B)</td><td>{brl(c['valor'][2028],3)}</td></tr>
<tr><td>Valor de cada kWh compensado de 2029 em diante (premissa: menos 100% do Fio B)</td><td>{brl(c['valor'][2029],3)}</td></tr>
<tr><td>Economia no 1º ano ({ANO_INICIO})</td><td>{brl(c['eco_ano1_min'],0)} a {brl(c['eco_ano1_max'],0)}</td></tr>
<tr><td>Custo de referência por kWp instalado</td><td>{brl(CUSTO_KWP_MIN,0)} a {brl(CUSTO_KWP_MAX,0)}</td></tr>
<tr><td><strong>Retorno do investimento (payback simples)</strong></td><td><strong>{pb_txt}</strong></td></tr>
</table></div>
<p><strong>Exemplo:</strong> para gerar 300 kWh por mês em {e(m['nome'])}, seriam necessários de {fnum(c['kwp_300_min'],1)} a {fnum(c['kwp_300_max'],1)} kWp de painéis, com custo de referência de {brl(c['kwp_300_min']*CUSTO_KWP_MIN,0)} a {brl(c['kwp_300_max']*CUSTO_KWP_MAX,0)}. Sistemas pequenos costumam custar mais por kWp; o seu orçamento pode sair diferente.</p>
<div class="alert"><strong>Isto é uma estimativa, não uma garantia.</strong> Premissas: taxa de desempenho de 70% a 80% (CEPEL/CRESESB); custo de R$ 2,91 a R$ 3,62 por Wp (média nacional da Greener, junho de 2026); toda a geração tratada como energia injetada e compensada, sem consumo simultâneo; tarifas congeladas nos valores de hoje; sem tributos, degradação dos painéis, manutenção, troca de inversor nem financiamento. Veja a <a href="{url('metodologia/')}">metodologia completa</a>.</div>

<h2>O que a Lei 14.300 muda para quem instala agora</h2>
<p>Quem pede a conexão hoje entra na regra de transição: sobre a energia que volta da rede como crédito, paga uma parte crescente do “Fio B” da distribuidora. Os créditos valem por 60 meses (art. 13).</p>
{lei_resumo()}
<p><a href="{url('lei-14300/')}">Entenda a Lei 14.300 em detalhes</a></p>

{cta_box(cidade_uf, t['sigla'])}
{parceiros_html(m['uf'])}

<h2>Fontes desta página</h2>
{fontes_cidade(m)}
<p class="small">Página publicada em {e(data_pub)}. Dados processados em {e(META['processado_em'])}. Conteúdo informativo; não é projeto de engenharia, proposta comercial nem recomendação de investimento. Encontrou um erro? Escreva para <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
"""
    desc = (f"Vale a pena energia solar em {nome_uf}? Irradiação do Atlas INPE, tarifa B1 da {t['sigla']} (ANEEL), "
            f"{fint(g['solar_n'])} sistemas instalados e estimativa transparente de geração e retorno.")
    path = f"municipio/{m['slug']}/"
    page(path, f"Energia solar em {nome_uf}: vale a pena? Dados oficiais e estimativa", desc, body,
         crumbs=[("Início", ""), ("Cidades", "cidades/"), (nome_uf, None)],
         extra_ld=[{"@context": "https://schema.org", "@type": "WebPage", "name": f"Energia solar em {nome_uf}",
                    "inLanguage": "pt-BR", "url": abs_url(path), "dateModified": date.today().isoformat(),
                    "publisher": {"@type": "Organization", "name": EMPRESA}}])
    return {"path": path, "m": m, "c": c}


def card(p):
    m, c = p["m"], p["c"]
    pb = f"{fnum(p['c']['pb_otimista'],1)}–{fnum(p['c']['pb_conservador'],1)} anos" if c["pb_otimista"] and c["pb_conservador"] else "—"
    return (f'<a class="card" data-busca="{e(m["nome"])} {e(m["uf"])}" href="{url(p["path"])}"><span class="tag">{e(m["uf"])}</span>'
            f'<strong style="display:block">{e(m["nome"])}</strong>'
            f'<span class="small">{fint(c["gen_mes_min"])}–{fint(c["gen_mes_max"])} kWh/mês por kWp · tarifa {brl(c["T"],2)}/kWh · retorno estimado {pb}</span></a>')


def home(pages, fila_n):
    cards = "".join(card(p) for p in sorted(pages, key=lambda p: p["m"]["nome"]))
    body = f"""
<h1>Vale a pena energia solar na sua cidade?</h1>
<p class="lead">Respostas por município com dados oficiais: o sol medido pelo INPE, a tarifa residencial homologada pela ANEEL, quantos sistemas já existem na cidade e uma estimativa de retorno com premissas explícitas.</p>
<div class="card"><label for="busca"><strong>Procure sua cidade</strong></label>
<input id="busca" type="search" placeholder="Digite o nome da cidade ou a UF" autocomplete="off">
<p class="small">{len(pages)} cidades publicadas. Uma cidade nova entra toda noite ({fila_n} na fila).</p></div>
<div class="grid g3">{cards}</div>
<p id="sem-resultado" class="muted" style="display:none">Essa cidade ainda não foi publicada. Escreva para <a href="mailto:{EMAIL}?subject={quote('Sugestão de cidade — Energia Solar no Município')}">{EMAIL}</a> e sugira.</p>

<h2>Como lemos os números</h2>
<div class="grid g3">
<div class="card"><strong>Sol</strong><p class="small">Irradiação no plano inclinado do Atlas Brasileiro de Energia Solar (INPE/LABREN), na sede do município.</p></div>
<div class="card"><strong>Tarifa</strong><p class="small">Tarifa residencial B1 vigente da distribuidora, publicada pela ANEEL, sem tributos.</p></div>
<div class="card"><strong>Regras</strong><p class="small">Transição do “Fio B” da Lei 14.300/2022 aplicada ano a ano no cálculo do retorno.</p></div>
</div>
<div class="alert">Os resultados são estimativas para comparar cidades e entender a ordem de grandeza. Não substituem a visita técnica nem um projeto. <a href="{url('metodologia/')}">Veja a metodologia</a>.</div>
{cta_box()}
{parceiros_html()}
"""
    page("", "Energia solar por município: vale a pena na sua cidade? | Energia Solar no Município",
         "Dados oficiais por cidade: irradiação do Atlas INPE, tarifa residencial da ANEEL, sistemas instalados e estimativa transparente de geração e retorno com a Lei 14.300.",
         body, script=True, extra_ld=[{"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NOME, "url": abs_url(""), "inLanguage": "pt-BR",
                                       "publisher": {"@type": "Organization", "name": EMPRESA}}])


def cidades(pages, fila):
    rows = "".join(
        f'<tr data-busca="{e(p["m"]["nome"])} {e(p["m"]["uf"])}"><td><a href="{url(p["path"])}">{e(p["m"]["nome"])}</a></td><td>{e(p["m"]["uf"])}</td>'
        f'<td>{fnum(p["c"]["H"],2)}</td><td>{brl(p["c"]["T"],3)}</td><td>{fint(p["m"]["gd"]["solar_n"])}</td></tr>'
        for p in sorted(pages, key=lambda p: (p["m"]["uf"], p["m"]["nome"])))
    prox = ", ".join(e(f"{MUN[i]['nome']} ({MUN[i]['uf']})") for i in fila[:10])
    body = f"""<h1>Cidades publicadas</h1>
<input id="busca" type="search" placeholder="Filtrar por cidade ou UF" autocomplete="off">
<div class="tbl"><table><tr><th>Cidade</th><th>UF</th><th>Sol (kWh/m².dia)</th><th>Tarifa B1 sem tributos</th><th>Sistemas solares</th></tr>{rows}</table></div>
<p id="sem-resultado" class="muted" style="display:none">Nenhuma cidade publicada com esse nome.</p>
<h2>Próximas na fila</h2><p>{prox or '—'}{' e outras' if len(fila) > 10 else ''}. São {len(fila)} cidades com mais de 100 mil habitantes aguardando publicação, uma por noite.</p>"""
    page("cidades/", "Cidades publicadas — Energia Solar no Município", "Lista das cidades com página de energia solar residencial: irradiação, tarifa e sistemas instalados.", body,
         crumbs=[("Início", ""), ("Cidades", None)], script=True)


def lei14300():
    body = f"""<h1>Lei 14.300/2022: o que muda para quem instala energia solar em casa</h1>
<p class="lead">A Lei nº 14.300, de 6 de janeiro de 2022, é o marco legal da micro e minigeração distribuída. Ela regula o Sistema de Compensação de Energia Elétrica (SCEE), em que a energia que sobra do seu telhado vai para a rede e volta como crédito.</p>
<h2>Os conceitos</h2>
<ul>
<li><strong>Microgeração:</strong> até 75 kW de potência instalada. Praticamente todo sistema residencial está aqui (art. 1º).</li>
<li><strong>Créditos:</strong> a energia injetada vira crédito em kWh, que abate o consumo e vale por 60 meses (art. 13).</li>
<li><strong>Valor mínimo faturável:</strong> a conta não fica zerada. A unidade continua pagando o mínimo previsto na regulamentação (art. 16).</li>
<li><strong>Fio B:</strong> são as componentes da tarifa que remuneram os ativos, a depreciação e a operação e manutenção da rede da distribuidora. É sobre elas que incide a cobrança da transição.</li>
</ul>
<h2>Quem tem a regra antiga até 2045</h2>
<p>Sistemas que já existiam em 7 de janeiro de 2022 ou cujo pedido de acesso foi protocolado em até 12 meses após a publicação da lei continuam com a regra anterior até 31 de dezembro de 2045, sem pagar o Fio B sobre a energia compensada (art. 26).</p>
<h2>Quem instala agora: a transição</h2>
{lei_resumo()}
<p>Depois de 2028, vale a regra do art. 17: as unidades passam a pagar as componentes não associadas ao custo da energia, abatidos os benefícios que a geração distribuída traz ao sistema, conforme cálculo da ANEEL a partir de diretrizes do CNPE. Como esse valor ainda depende de regulação, nossas estimativas usam 100% do Fio B a partir de 2029, que é uma premissa prudente, não uma previsão.</p>
<h2>Na prática</h2>
<p>A energia usada no mesmo instante em que é gerada não passa pela rede e não paga Fio B. Por isso, quem consome mais durante o dia tende a ter retorno melhor. Nossa estimativa ignora esse efeito, para não superestimar a economia.</p>
<p class="small">Texto legal: {fonte('lei')}, consultado em 20/11/2026. Este resumo é informativo e não substitui a leitura da lei e da regulamentação da ANEEL (Resolução Normativa nº 1.000/2021 e alterações).</p>
{cta_box()}"""
    page("lei-14300/", "Lei 14.300/2022 e o Fio B: regras para energia solar residencial", "Resumo da Lei 14.300/2022: créditos de 60 meses, regra antiga até 2045 e a transição do Fio B (60% em 2026, 75% em 2027, 90% em 2028).", body,
         crumbs=[("Início", ""), ("Lei 14.300", None)])


def metodologia():
    f = META["fontes"]
    body = f"""<h1>Metodologia e fontes</h1>
<p class="lead">Cada número das páginas vem de uma base pública oficial ou de uma premissa explícita com fonte. Não inventamos dados. Quando falta um dado, o município não é publicado.</p>
<h2>Dados oficiais</h2>
<ul class="src">
<li><strong>Irradiação solar:</strong> {fonte('atlas')}. Usamos a irradiação no plano inclinado (inclinação igual à latitude, voltado para o norte) do arquivo das sedes municipais, médias anuais de 1999 a 2015, em Wh/m² por dia. Resolução de 0,1° (cerca de 10 km). Baixado em {f['atlas']['baixado_em']}. Fonte: LABREN/CCST/INPE – Brasil. A base é usada só como dado de entrada das estimativas, com citação, como o INPE pede.</li>
<li><strong>Distribuidora:</strong> a que concentra os registros de geração distribuída com o código IBGE do município na base da ANEEL. Se outra tiver 5% ou mais dos registros, a página informa.</li>
<li><strong>Tarifa:</strong> {fonte('tarifas')}. Filtro: Tarifa de Aplicação, subgrupo B1, modalidade Convencional, classe e subclasse Residencial, vigente em {br_date(META['data_referencia'])}. TUSD + TE, em R$/MWh convertidos para R$/kWh, sem ICMS, PIS/Cofins, bandeira ou iluminação pública. Conjunto gerado pela ANEEL em {br_date(f['tarifas']['gerado'])}.</li>
<li><strong>Fio B:</strong> {fonte('componentes')}, componente TUSD_FioB do mesmo recorte e da mesma vigência. Conjunto gerado em {br_date(f['componentes']['gerado'])}.</li>
<li><strong>Sistemas instalados:</strong> {fonte('gd')}, empreendimentos com fonte “Radiação solar”, referência {e(f['gd']['periodo'])}, conjunto gerado em {br_date(f['gd']['gerado'])}.</li>
<li><strong>População e código do município:</strong> {fonte('ibge')}, estimativa de 2026.</li>
</ul>
<h2>Como calculamos a estimativa</h2>
<ol>
<li><strong>Geração por kWp</strong> = irradiação diária (kWh/m²) × dias × taxa de desempenho. Usamos taxa de desempenho de 70% a 80%, faixa que o {fonte('cepel')} indica para sistemas residenciais bem ventilados e sem sombra no Brasil.</li>
<li><strong>Valor do kWh compensado</strong> = tarifa B1 (TUSD + TE) menos o percentual do Fio B do ano: 75% em 2027, 90% em 2028 (Lei 14.300, art. 27) e, por prudência, 100% de 2029 em diante.</li>
<li><strong>Custo</strong> = R$ {fnum(CUSTO_KWP_MIN,0)} a R$ {fnum(CUSTO_KWP_MAX,0)} por kWp, preço médio nacional do sistema instalado em junho de 2026 para 4 kWp e 2 kWp, segundo a {fonte('greener')}.</li>
<li><strong>Retorno (payback simples)</strong> = anos até a economia acumulada, a partir de {ANO_INICIO}, igualar o custo. O cenário favorável combina 80% de desempenho com o custo menor; o conservador, 70% com o custo maior.</li>
</ol>
<h2>O que a estimativa não considera</h2>
<ul>
<li>Tributos e bandeiras: a economia real na conta tende a ser maior que a calculada, mas depende das regras de cada estado.</li>
<li>Consumo simultâneo, que não paga Fio B. Tratamos toda a geração como injetada, o que reduz a economia estimada.</li>
<li>Reajustes de tarifa, inflação, degradação dos painéis, manutenção, troca de inversor, seguro e juros de financiamento.</li>
<li>Sombra, orientação e inclinação reais do telhado, e o valor mínimo faturável da conta.</li>
</ul>
<p>Por isso, a estimativa não é promessa de economia. Use-a para comparar cidades e conferir se um orçamento faz sentido.</p>
<h2>Atualização</h2>
<p>Uma cidade nova é publicada toda noite. Os dados são reprocessados periodicamente; cada página mostra a data. Correções: <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>"""
    page("metodologia/", "Metodologia e fontes — Energia Solar no Município", "Fontes oficiais (INPE/LABREN, ANEEL, IBGE) e as premissas da estimativa de geração, economia e retorno da energia solar residencial.", body,
         crumbs=[("Início", ""), ("Metodologia", None)])


def orcamentos():
    body = f"""<h1>Peça orçamentos de energia solar</h1>
<p class="lead">Por enquanto, os pedidos são recebidos só por e-mail, em <a href="mailto:{EMAIL}">{EMAIL}</a>, com o assunto “Orçamento solar — sua cidade/UF”.</p>
<h2>Como funciona</h2>
<ol>
<li>Clique no botão abaixo ou no botão da página da sua cidade. Seu e-mail abre com o assunto e um roteiro prontos.</li>
<li>Preencha o consumo médio em kWh (está na conta de luz), o tipo de telhado e a cidade. Não mande documentos nem foto da conta agora.</li>
<li>Mantenha o texto de consentimento. Sem ele, não conseguimos responder.</li>
<li>Se quiser que empresas instaladoras entrem em contato com orçamentos, escreva SIM no campo de compartilhamento. Esse campo é opcional.</li>
</ol>
<p>A {EMPRESA} não instala sistemas solares e não é responsável por preço, prazo, garantia ou resultado de serviços de terceiros. Compare propostas, confira a homologação dos equipamentos no Inmetro e exija contrato.</p>
{cta_box()}
{parceiros_html()}"""
    page("orcamentos/", "Peça orçamentos de energia solar — Energia Solar no Município", "Peça orçamentos de energia solar residencial por e-mail, com consentimento LGPD explícito e sem custo.", body,
         crumbs=[("Início", ""), ("Peça orçamentos", None)])


def aviso():
    body = f"""<h1>Aviso legal</h1>
<p class="small">Atualizado em {hoje()}.</p>
<p>Este site é mantido pela {EMPRESA} (CNPJ {CNPJ}), empresa de consultoria empresarial.</p>
<h2>Conteúdo informativo</h2>
<p>As páginas reúnem dados públicos oficiais e estimativas com premissas explícitas. Não são projeto de engenharia, proposta comercial, laudo nem recomendação de investimento.</p>
<h2>Sem garantia de economia</h2>
<p>Não prometemos nem garantimos economia, geração ou prazo de retorno. Os resultados reais dependem do local, do telhado, do consumo, do equipamento, da instalação, das tarifas e da regulação, que podem mudar.</p>
<h2>Não somos órgão público nem distribuidora</h2>
<p>Este site não é da ANEEL, do INPE, do IBGE, do CEPEL ou de qualquer distribuidora de energia e não fala em nome deles.</p>
<h2>Não instalamos sistemas</h2>
<p>A {EMPRESA} não vende nem instala sistemas fotovoltaicos. Quando o visitante autoriza expressamente, o pedido pode ser encaminhado a empresas instaladoras, que respondem pelos próprios serviços.</p>
<h2>Publicidade</h2>
<p>Se houver anúncios ou links de parceiros, eles aparecerão com o rótulo “Publicidade”, como recomenda o CONAR, e poderemos receber comissão. Os dados e as estimativas não mudam por causa disso. Hoje o site não tem anunciantes.</p>
<h2>Uso dos dados de terceiros</h2>
<p>Os dados do Atlas Brasileiro de Energia Solar pertencem ao INPE (LABREN/CCST/INPE – Brasil) e são usados como dado de entrada das estimativas, com citação. Os dados da ANEEL e do IBGE são abertos. Cada página informa a fonte e a data.</p>
<h2>Correções</h2>
<p>Encontrou um erro? Escreva para <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>"""
    page("aviso-legal/", "Aviso legal — Energia Solar no Município", "Conteúdo informativo, estimativas sem garantia de economia, publicidade identificada e responsável pelo site.", body,
         crumbs=[("Início", ""), ("Aviso legal", None)])


def privacidade():
    body = f"""<h1>Política de privacidade</h1>
<p class="small">Atualizada em {hoje()}.</p>
<h2>Quem é a controladora</h2>
<p>{EMPRESA}, CNPJ {CNPJ}. Contato para assuntos de privacidade: <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
<h2>Quais dados tratamos</h2>
<p>O site não tem formulário, não usa cookies e não usa ferramentas de análise ou rastreamento. Só tratamos o que você nos envia por e-mail: nome, endereço de e-mail e as informações do pedido de orçamento (cidade, bairro se informado, consumo, tipo de ligação e de telhado, se o imóvel é próprio e outro contato, se você quiser).</p>
<p>A hospedagem (GitHub Pages) pode registrar dados técnicos de acesso, como o endereço IP, para segurança e funcionamento, conforme a política do GitHub.</p>
<h2>Para que usamos e com qual base legal</h2>
<ul>
<li><strong>Responder ao seu pedido por e-mail:</strong> com base no seu consentimento (LGPD, art. 7º, I), dado ao enviar o e-mail com o texto de consentimento.</li>
<li><strong>Encaminhar o pedido a até 3 empresas instaladoras:</strong> somente com um segundo consentimento, separado e opcional, quando você escreve SIM no campo indicado. Sem esse SIM, seus dados não saem da {EMPRESA}.</li>
</ul>
<h2>Compartilhamento</h2>
<p>Não vendemos seus dados. O e-mail é operado pelo provedor do nosso endereço (Google/Gmail). As empresas instaladoras só recebem os dados com a sua autorização expressa e passam a tratá-los como controladoras independentes, para enviar o orçamento.</p>
<h2>Por quanto tempo guardamos</h2>
<p>Pelo tempo necessário para responder ao pedido e, depois, só o que for razoável para cumprir obrigações legais ou para nos defender em eventual reclamação. Você pode pedir a eliminação a qualquer momento, quando a lei permitir.</p>
<h2>Seus direitos e como revogar</h2>
<p>Você pode pedir confirmação, acesso, correção, eliminação e informações sobre o uso dos seus dados (LGPD, art. 18). Para revogar o consentimento, responda qualquer e-mail nosso com a palavra <strong>REVOGAR</strong> ou escreva para <a href="mailto:{EMAIL}?subject=REVOGAR">{EMAIL}</a>. Você também pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD).</p>
<h2>Cookies</h2>
<p>Este site não usa cookies. Se isso mudar, esta política será atualizada antes.</p>"""
    page("privacidade/", "Política de privacidade (LGPD) — Energia Solar no Município", "Como a MM Consultoria Corporativa Ltda. trata os dados enviados por e-mail nos pedidos de orçamento solar, com consentimento separado para compartilhamento.", body,
         crumbs=[("Início", ""), ("Privacidade", None)])


def notfound():
    body = f"<h1>Página não encontrada</h1><p>O endereço pode ter mudado ou a cidade ainda não foi publicada.</p><p><a href='{url()}'>Voltar ao início</a> ou veja as <a href='{url('cidades/')}'>cidades publicadas</a>.</p>"
    page("404.html", "Página não encontrada — Energia Solar no Município", "Página não encontrada.", body)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    (OUT / "assets/style.css").write_text(CSS.strip(), encoding="utf-8")
    (OUT / "assets/app.js").write_text(JS.strip(), encoding="utf-8")
    pub = load_pub()
    fila = [i for i in load("fila.json") if i not in {p["ibge"] for p in pub} and i in MUN]
    pages = [city_page(MUN[p["ibge"]], p["data"]) for p in pub if p["ibge"] in MUN]
    home(pages, len(fila)); cidades(pages, fila); lei14300(); metodologia(); orcamentos(); aviso(); privacidade(); notfound()
    paths = ["", "cidades/", "lei-14300/", "metodologia/", "orcamentos/", "aviso-legal/", "privacidade/"] + [p["path"] for p in pages]
    today = date.today().isoformat()
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"<url><loc>{abs_url(p)}</loc><lastmod>{today}</lastmod></url>\n" for p in paths) + "</urlset>\n"
    (OUT / "sitemap.xml").write_text(sm, encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {abs_url('sitemap.xml')}\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site gerado: {len(pages)} cidades, {len(paths)} URLs no sitemap, {len(fila)} na fila -> {OUT}")


if __name__ == "__main__":
    main()
