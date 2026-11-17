# Monitor de emissões por fogo — Bioma × UF

Este é o repositório principal do monitor de emissões. Os scripts usados no Earth Engine Code Editor também ficam no repositório auxiliar `users/workspaceipam/SEEG`.

## Artefatos

- [`index.html`](index.html): dashboard autocontido, com dados e Chart.js embutidos; funciona localmente e no GitHub Pages.
- [`data/consolidado_monitor_emissoes_gases_bioma_uf.csv`](data/consolidado_monitor_emissoes_gases_bioma_uf.csv): tabela mensal (CO₂, CH₄ e N₂O em CO₂e) para Looker Studio e para reconstruir o dashboard.
- [`data/area_territorio_bioma_uf.csv`](data/area_territorio_bioma_uf.csv): área do território por bioma × UF, usada no cálculo de densidade (t/km²).
- [`src/`](src/): builder Python e pipeline de estatísticas/exportação.
- [`gee/`](gee/): script atual do primeiro ensaio (saída mensal com três bandas), referência da versão anterior de uma banda e script de investigação dos mapas de carbono. Os scripts do Code Editor também são mantidos no repositório GEE auxiliar.

O consolidado contém 32.768 linhas, 94 meses (2019-01 a 2026-10) e 27 UFs. No total do período: 134,5 Mha queimados e 3,65 Gt CO₂e (CO₂ 3,37 Gt; CH₄ 176 Mt CO₂e; N₂O 108 Mt CO₂e). Cada linha representa a agregação mensal por bioma, UF e classe. No Looker Studio, conecte o CSV acima e use `Ano`, `mes`, `Bioma`, `SIGLA_UF` e as classes como dimensões; `Área km²`, `Emissão CO2 (t)`, `Emissão CH4 (t CO2e)`, `Emissão N2O (t CO2e)` e `Emissão CO2e total (t)` são métricas somáveis.

## Destaques do mês

[`destaques.html`](https://wallyboy22.github.io/emiss_fire_monitor/destaques.html) é um relatório mensal no formato dos destaques do Monitor do Fogo, com a emissão ao lado da área queimada em cada bloco: Brasil (mês e acumulado do ano), biomas e estados (mapa e ranking), o bioma e o estado que mais emitiram, e uma página sobre o que a emissão acrescenta à área (emissão por hectare, gases, coberturas). O mês vem do seletor ou de `?m=AAAA-MM` (o painel abre os destaques do último mês do período filtrado); sem parâmetro, mostra o último mês disponível. A página consulta a API pública do Monitor do Fogo para comparar a área do mês com a base de cálculo da emissão, e o botão de impressão gera um PDF de 6 páginas em A4 paisagem.

- [`src/destaques.py`](src/destaques.py): gera a página, chamado pelo `build_dashboard.py`.
- [`src/geometrias.py`](src/geometrias.py): baixa e simplifica os contornos de biomas (IBGE, via GEE) e UFs (malha do IBGE) para `data/geo/`; rode uma vez.

## Comparação externa

- [`src/comparacao_externa.py`](src/comparacao_externa.py): soma o GFED5.1 (Zenodo), o SEEG 14 (fogo em vegetação nativa, CSVs do Drive) e o CAMS GFAS (API do ADS, requer chave) no Brasil, com máscara dos limites do IBGE, e grava [`data/externo/comparacao_anual.csv`](data/externo/comparacao_anual.csv) (área queimada em ha; CO₂, CH₄, N₂O e matéria seca em t). O dashboard mostra a comparação quando esse arquivo existe.

## Reconstruir o dashboard

```bash
python -m pip install -r requirements.txt
python src/build_dashboard.py
```

O builder usa o CSV consolidado versionado. Se CSVs mensais forem colocados em `data/monthly/`, eles serão usados em preferência ao consolidado. O HTML resultante é escrito em `index.html` e não busca CSV, CDN ou outros recursos externos.

## Earth Engine

`src/primeiro_ensaio.py` é a versão Python de `gee/primeiro_ensaio.js` e exporta as imagens mensais de emissão (`--submit`; sem a opção, apenas lista; `--test` compara com o asset publicado). A biomassa seca é obtida do carbono por `carbono / 0,47`.

`src/stats_do_primeiro_ensaio.py` exporta tabelas mensais por Bioma × UF × classe. Requer Earth Engine autenticado localmente. A opção `--submit` inicia tarefas remotas; sem ela, o script apenas lista as tarefas. As exportações são destinadas à pasta Drive `monitoramento-sentinel`.

`gee/primeiro_ensaio.js` começa em modo de prévia, sem criar exports. A prévia empilha as três bandas calculadas por mês e a área queimada para inspeção no mapa/Inspector. Use `MONTHS_TO_PROCESS` para limitar o teste; depois de validar os pixels e o destino, altere `EXPORT_IMAGES` para `true`.

`gee/investigando_primeiro_ensaio.js` compara a emissão mensal existente com recálculos usando o QCN original e `c_rect_col11_2019`. Edite `YEAR_MONTHS`; para análise nacional exata, use exportação em batch, pois reduções síncronas a 30 m podem exceder o timeout.

## GitHub Pages

O workflow em `.github/workflows/pages.yml` publica o dashboard a cada atualização da branch `main`. A página fica em <https://wallyboy22.github.io/emiss_fire_monitor/>.

## Nota de validação

Os totais do novo consolidado Bioma × UF diferem ligeiramente da antiga tabela somente por bioma (área: -0,00145%; emissão: -0,00133%), principalmente na Amazônia e no Pantanal. A causa espacial segue em investigação; considere essa diferença ao comparar séries.
