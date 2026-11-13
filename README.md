# Monitor de emissões por fogo — Bioma × UF

Este é o repositório principal do monitor de emissões. Os scripts usados no Earth Engine Code Editor também ficam no repositório auxiliar `users/workspaceipam/SEEG`.

## Artefatos

- [`index.html`](index.html): dashboard autocontido, com dados e Chart.js embutidos; funciona localmente e no GitHub Pages.
- [`data/consolidado_monitor_emissoes_bioma_uf.csv`](data/consolidado_monitor_emissoes_bioma_uf.csv): tabela mensal para Looker Studio e para reconstruir o dashboard.
- [`src/`](src/): builder Python e pipeline de estatísticas/exportação.
- [`gee/`](gee/): script original do primeiro ensaio e script de investigação dos mapas de carbono. O último também é mantido no repo GEE auxiliar em `SEEG14/RETIFICACAO/`.

O consolidado contém 32.351 linhas, 93 meses (2019-01 a 2026-09) e 27 UFs. Cada linha representa a agregação mensal por bioma, UF e classe. No Looker Studio, conecte o CSV acima e use `Ano`, `mes`, `Bioma`, `SIGLA_UF` e as classes como dimensões; `Área km²` e `Emissão CO2` são métricas somáveis.

## Reconstruir o dashboard

```bash
python -m pip install -r requirements.txt
python src/build_dashboard.py
```

O builder usa o CSV consolidado versionado. Se CSVs mensais forem colocados em `data/monthly/`, eles serão usados em preferência ao consolidado. O HTML resultante é escrito em `index.html` e não busca CSV, CDN ou outros recursos externos.

## Earth Engine

`src/stats_do_primeiro_ensaio.py` exporta tabelas mensais por Bioma × UF × classe. Requer Earth Engine autenticado localmente. A opção `--submit` inicia tarefas remotas; sem ela, o script apenas lista as tarefas. As exportações são destinadas à pasta Drive `monitoramento-sentinel`.

`gee/investigando_primeiro_ensaio.js` compara a emissão mensal existente com recálculos usando o QCN original e `c_rect_col11_2019`. Edite `YEAR_MONTHS`; para análise nacional exata, use exportação em batch, pois reduções síncronas a 30 m podem exceder o timeout.

## GitHub Pages

O workflow em `.github/workflows/pages.yml` publica o dashboard a cada atualização da branch `main`. A página fica em <https://wallyboy22.github.io/emiss_fire_monitor/>.

## Nota de validação

Os totais do novo consolidado Bioma × UF diferem ligeiramente da antiga tabela somente por bioma (área: -0,00145%; emissão: -0,00133%), principalmente na Amazônia e no Pantanal. A causa espacial segue em investigação; considere essa diferença ao comparar séries.
