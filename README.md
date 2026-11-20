# Energia Solar no Município

Diretório estático, em pt-BR, que responde “vale a pena energia solar em <cidade>?” com dados oficiais:
irradiação do Atlas Brasileiro de Energia Solar (INPE/LABREN, 2017), tarifa residencial B1 e componente Fio B
(ANEEL, dados abertos), sistemas de micro e minigeração distribuída instalados (ANEEL) e população (IBGE).
Mantido pela MM Consultoria Corporativa Ltda. (CNPJ 49.399.582/0001-10). **Este site não é a ANEEL nem o INPE.**

Endereço público: <https://advogadomarciopinheiro-cmd.github.io/energia-solar-municipio/>

## Arquivos

- `scripts/fetch_and_process.py` – baixa (se faltar; `--refresh` força) e processa as bases oficiais de `data/raw/` em
  `data/processed/municipios.json` e `meta.json` (municípios com 100 mil habitantes ou mais). Requer `pandas` e `pyarrow`.
- `scripts/build.py` – gera `site/` (home com busca, cidades, páginas municipais, Lei 14.300, metodologia, peça orçamentos,
  aviso legal, privacidade, 404, sitemap, robots). Só biblioteca padrão. Premissas da estimativa e a lista `PARCEIROS = []`
  ficam no topo do arquivo (lista vazia oculta a seção; preenchida, aparece com o rótulo **Publicidade**, CONAR).
- `nightly.py` – publica UMA cidade da fila (`data/processed/fila.json`) por execução, sem duplicar (`publicadas.json`,
  log em `nightly_log.jsonl`).
- `publish_nightly.sh` – roda o nightly, reconstrói, commita em `main`, publica `site/` no branch `gh-pages` e confere
  HTTP 200 da home e da página nova (log em `publish_log.jsonl`; sai com código 2 se alguma URL não responder 200).
  `SKIP_NIGHTLY=1 ./publish_nightly.sh` só republica.
- `partners/prospectos.csv` – possíveis parceiros, com e-mail comercial publicado e a URL de origem. Nenhum contato foi feito.

## Gerar localmente

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_and_process.py      # baixa ~1,8 GB na primeira vez
python3 scripts/build.py
python3 -m http.server 8080 --directory site        # BASE_URL padrão é /energia-solar-municipio/
```

## Estimativa (resumo)

Geração por kWp = irradiação no plano inclinado × dias × taxa de desempenho 70–80% (CEPEL/CRESESB, 2014).
Valor do kWh compensado = TUSD + TE (sem tributos) − percentual do Fio B (Lei 14.300, art. 27: 75% em 2027,
90% em 2028; premissa de 100% de 2029 em diante). Custo de R$ 2.910 a R$ 3.620 por kWp (Greener, jun/2026).
Payback simples a partir de 2027. Não é garantia de economia.

## Licença dos dados

O Atlas do INPE pede citação (“LABREN/CCST/INPE – Brasil”) e não permite reprodução da base para fins comerciais sem
autorização; aqui ele é usado só como dado de entrada, e a base bruta não é versionada (`data/raw/` fica fora do git).
