"""Une os CSVs mensais do monitor e gera um dashboard HTML autocontido (Chart.js embutido).

Entrada: CSVs de `stats_do_primeiro_ensaio.py` (Bioma × UF × classe × mês), com área e
emissões por gás (CO2, CH4 e N2O em CO2e). Saída: CSV consolidado + HTML de arquivo único.

Os dados vão para o HTML como uma tabela colunar compacta (uma linha por
mês × bioma × UF × classe); todos os filtros e agregações acontecem no navegador.

Layouts suportados (detectados pelo local do script):
  - CCAL/MONITOR_EMISSOES/v00/construir_dashboard.py
  - <repo emiss_fire_monitor>/src/build_dashboard.py
"""
import argparse
import json
from pathlib import Path

import pandas as pd

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import primeiro_ensaio as _pe  # noqa: E402  (fatores usados nas imagens; fonte única para a página de método)

HERE = Path(__file__).resolve().parent
if HERE.name == "src":  # repositório público
    ROOT = HERE.parent
    DEFAULTS = {
        "data": ROOT / "data" / "monthly",
        "csv": ROOT / "data" / "consolidado_monitor_emissoes_gases_bioma_uf.csv",
        "html": ROOT / "index.html",
        "chart_js": ROOT / "assets" / "chart.umd.min.js",
        "csv_href": "data/consolidado_monitor_emissoes_gases_bioma_uf.csv",
        "territory": ROOT / "data" / "area_territorio_bioma_uf.csv",
    }
else:  # CCAL/MONITOR_EMISSOES/v00
    DEFAULTS = {
        "data": HERE / "data_bioma_uf_gases",
        "csv": HERE / "consolidado_monitor_emissoes_gases_bioma_uf.csv",
        "html": HERE / "dashboard_monitor_emissoes.html",
        "chart_js": HERE / "chart.umd.min.js",
        "csv_href": "consolidado_monitor_emissoes_gases_bioma_uf.csv",
        "territory": HERE / "area_territorio_bioma_uf.csv",
    }

# Ordem = ordem das cores categóricas validadas (os três biomas que mais emitem ficam nas três primeiras)
BIOMES = ["Amazônia", "Cerrado", "Pantanal", "Caatinga", "Mata Atlântica", "Pampa"]
AREA_HA = "Área ha"
GAS_COLS = {
    "co2": "Emissão CO2 (t)",
    "ch4": "Emissão CH4 (t CO2e)",
    "n2o": "Emissão N2O (t CO2e)",
}
TOTAL_COL = "Emissão CO2e total (t)"
CLASS_LEVELS = ["Nível 0", "Nível 1_1", "Nível 4"]

# Grupos de cobertura (Nível 1_1) com as cores da legenda MapBiomas
# (MAPBIOMAS-CARBONO/COLLECTION_00/toolkits/view/v00/contracts/00_catalog_landcover.js).
# A ordem alterna tons para que vizinhos na pilha fiquem distinguíveis
# (validado: daltonismo ΔE >= 12,9 e visão normal ΔE >= 15,7 entre vizinhos).
COVER = [
    ["Formação Florestal", "#1f8d49"],
    ["Pastagem", "#edde8e"],
    ["Campo Alagado e Área Pantanosa", "#519799"],
    ["Agricultura", "#e974ed"],
    ["Formação Savânica", "#7dc975"],
    ["Silvicultura", "#7a5900"],
    ["Formação Campestre", "#d6bc74"],
    ["Mosaico de Usos", "#ffefc3"],
]
COVER_OTHER = ["Outras classes", "#9c8f80"]
COVER_SHORT = {
    "Formação Florestal": "Florestal", "Pastagem": "Pastagem", "Campo Alagado e Área Pantanosa": "Campo alagado",
    "Agricultura": "Agricultura", "Formação Savânica": "Savânica", "Silvicultura": "Silvicultura",
    "Formação Campestre": "Campestre", "Mosaico de Usos": "Mosaico", "Outras classes": "Outras",
}
# cor por código de classe (mesmo catálogo; 12 = #d6bc74)
CLASS_COLORS = {
    3: "#1f8d49", 4: "#7dc975", 5: "#04381d", 6: "#007785", 7: "#228c70", 9: "#7a5900", 11: "#519799",
    12: "#d6bc74", 13: "#af2ab4", 15: "#edde8e", 18: "#e974ed", 19: "#c27ba0", 20: "#db7093", 21: "#ffefc3",
    29: "#ad5100", 32: "#fc8114", 35: "#9065d0", 36: "#d082de", 39: "#f5b3c8", 40: "#c71585", 41: "#f54ca9",
    46: "#d68fe2", 47: "#9932cc", 48: "#e6ccff", 49: "#02d659", 50: "#ffaa5f", 62: "#ff69b4", 77: "#86b074",
}


CODE_NAMES = {
    3: "Formação Florestal", 4: "Formação Savânica", 5: "Mangue", 6: "Floresta Alagável", 7: "Savana Alagada",
    9: "Silvicultura", 11: "Campo Alagado e Área Pantanosa", 12: "Formação Campestre", 15: "Pastagem",
    20: "Cana", 21: "Mosaico de Usos", 35: "Dendê", 39: "Soja", 40: "Arroz", 41: "Outras Lavouras Temporárias",
    46: "Café", 47: "Citrus", 48: "Outras Lavouras Perenes", 49: "Restinga Arbórea", 50: "Restinga Herbácea",
    62: "Algodão", 77: "Formação Herbácea Arbustiva",
}


def _pool_coefs(expr):
    """'0.26*AGB+DW+LI' -> {'AGB': 0.26, 'DW': 1, 'LI': 1}"""
    out = {"AGB": 0.0, "DW": 0.0, "LI": 0.0}
    for term in expr.replace(" ", "").split("+"):
        k, _, var = term.rpartition("*")
        out[var] += float(k) if k else 1.0
    return out


def method_payload():
    return {
        "bioma": {b: {cat: {**v, "coef": _pool_coefs(v["c_pool"])} for cat, v in cats.items()}
                  for b, cats in _pe.FATORES_POR_BIOMA.items()},
        "ef": _pe.FATORES_POR_GAS,
        "gwp": _pe.GWP_AR5,
        "classes": {cat: [{"id": c, "name": CODE_NAMES.get(c, str(c)), "color": CLASS_COLORS.get(c, "#9c8f80")}
                          for c in codes] for cat, codes in _pe.CLASSES.items()},
        "antropic": sorted(_pe.ANTROPICAS),
        "carbon_fraction": _pe.CARBON_FRACTION,
        "last_cov_year": _pe.LAST_COVERAGE_YEAR,
    }


def load_all(data_dir, csv_path):
    files = sorted(Path(data_dir).glob("*.csv"))
    if files:
        df = pd.concat([pd.read_csv(fp) for fp in files], ignore_index=True)
    elif Path(csv_path).exists():
        df = pd.read_csv(csv_path)
    else:
        raise SystemExit(f"Nenhum CSV em {data_dir} nem consolidado em {csv_path}")
    missing = [c for c in [AREA_HA, *GAS_COLS.values(), TOTAL_COL, "SIGLA_UF"] if c not in df.columns]
    if missing:
        raise SystemExit(f"Colunas ausentes nos CSVs: {missing}")
    key = ["Ano", "mes", "bioma_id", "uf_id", "class_int"]
    dups = int(df.duplicated(key).sum())
    if dups:
        raise SystemExit(f"{dups} linhas duplicadas na chave {key}")
    df["ym"] = df["Ano"].astype(int).astype(str) + "-" + df["mes"].astype(int).astype(str).str.zfill(2)
    return df, bool(files)


def build_payload(df, territory):
    months = sorted(df["ym"].unique())
    m_idx = {m: i for i, m in enumerate(months)}
    b_idx = {b: i for i, b in enumerate(BIOMES)}
    unknown = set(df["Bioma"]) - set(BIOMES)
    if unknown:
        raise SystemExit(f"Biomas desconhecidos: {unknown}")

    ufs = df[["SIGLA_UF", "UF"]].drop_duplicates().sort_values("SIGLA_UF")
    uf_list = [{"sigla": s, "nome": n} for s, n in zip(ufs["SIGLA_UF"], ufs["UF"])]
    u_idx = {u["sigla"]: i for i, u in enumerate(uf_list)}

    cls = df[["class_int", *CLASS_LEVELS]].drop_duplicates("class_int").sort_values("class_int")
    class_list = [{"id": int(r["class_int"]), "color": CLASS_COLORS.get(int(r["class_int"]), COVER_OTHER[1]),
                   **{lv: r[lv] for lv in CLASS_LEVELS}}
                  for _, r in cls.iterrows()]
    c_idx = {c["id"]: i for i, c in enumerate(class_list)}

    def r1(s):
        return [round(float(v), 1) for v in s]

    facts = {
        "m": [m_idx[v] for v in df["ym"]],
        "b": [b_idx[v] for v in df["Bioma"]],
        "u": [u_idx[v] for v in df["SIGLA_UF"]],
        "c": [c_idx[int(v)] for v in df["class_int"]],
        "a": r1(df[AREA_HA]),
        **{g: r1(df[col]) for g, col in GAS_COLS.items()},
    }
    terr = []
    for _, t in territory.iterrows():
        if t["Bioma"] in b_idx and t["SIGLA_UF"] in u_idx:
            terr.append([b_idx[t["Bioma"]], u_idx[t["SIGLA_UF"]], round(float(t["area_km2"]), 1)])
    missing = {(b, u) for b, u in zip(df["Bioma"], df["SIGLA_UF"])} - set(
        zip(territory["Bioma"], territory["SIGLA_UF"]))
    if missing:
        raise SystemExit(f"Bioma × UF sem área de território: {sorted(missing)}")
    known = {name for name, _ in COVER}
    cover = COVER + ([COVER_OTHER] if set(df["Nível 1_1"]) - known else [])
    return {"months": months, "biomes": BIOMES, "ufs": uf_list, "classes": class_list,
            "facts": facts, "territory": terr, "cover": cover, "cover_short": COVER_SHORT,
            "method": method_payload()}


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de Emissões por Fogo</title>
<meta name="description" content="Emissões mensais de CO2, CH4 e N2O por queima de vegetação no Brasil, por bioma, UF e classe de cobertura.">
<script>
__CHART_JS__
</script>
<style>
:root {
  color-scheme: light;
  --page: #f3ede2; --surface: #fbf8f2; --ink: #2a2119; --ink-2: #5b4a3b; --muted: #7d6b58;
  --grid: #e6dccb; --axis: #cbbca4; --ring: rgba(70,50,30,0.12); --seam: rgba(70,50,30,0.35);
  --accent: #9a4f26; --accent-weak: #ecd8c6; --on-accent: #fbf8f2;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --s6: #008300; --s7: #6250d6;
  --nat: #1f8d49; --ant: #ffefc3;
  --up: #a12b2b; --down: #1f6b3a;
  --ramp: #f7ece2,#f0d4bb,#e5b08c,#d18659,#b05c31,#7d3818; --ramp-ink-flip: 3;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #16120e; --surface: #201b16; --ink: #f2ece2; --ink-2: #cdbfac; --muted: #9c8c78;
  --grid: #2f2821; --axis: #463b30; --ring: rgba(255,240,220,0.10); --seam: rgba(0,0,0,0.45);
  --accent: #d98c5f; --accent-weak: #4d3222; --on-accent: #16120e;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #0ca30c; --s7: #9085e9;
  --nat: #2fa35c; --ant: #e8d9a8;
  --up: #e66767; --down: #4cbf72;
  --ramp: #33281f,#4e3324,#74432a,#a35b33,#d0804e,#f0b184; --ramp-ink-flip: 99;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--page); color: var(--ink);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 1500px; margin: 0 auto; padding: 0 16px 48px; }
header { padding: 28px 0 18px; display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
header .titles { flex: 1 1 520px; }
.seg.small button { font-size: 12px; padding: 5px 10px; min-height: 26px; }
header h1 { margin: 0 0 6px; font-size: 24px; font-weight: 650; letter-spacing: -0.01em; }
header p { margin: 0; color: var(--ink-2); max-width: 820px; }
header .meta { margin-top: 8px; font-size: 12.5px; color: var(--muted); }

/* ---- filtros: barra no topo (telas estreitas) ou coluna lateral (>= 1100px) ---- */
.layout { display: block; }
.content { min-width: 0; }
.filters { position: sticky; top: 0; z-index: 10; background: var(--page);
  border-bottom: 1px solid var(--grid); margin: 0 -16px 20px; padding: 0 16px 8px; }
.filters.stuck { box-shadow: 0 6px 12px -10px rgba(40,25,10,0.45); }
.fhead { padding: 10px 0 8px; }
.fhead .slice { font-size: 13px; color: var(--ink-2); line-height: 1.35; }
.fhead .slice b { color: var(--ink); font-weight: 650; }
.fbody { display: grid; gap: 10px 16px; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  max-height: 55vh; overflow-y: auto; padding-bottom: 6px; }
.fgroup { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.flabel { font-size: 11.5px; color: var(--muted); font-weight: 650; text-transform: uppercase; letter-spacing: .04em; }
.ftoggle { display: flex; width: 100%; justify-content: center; align-items: center; gap: 6px; margin-top: 4px;
  font: inherit; font-size: 12.5px; color: var(--ink-2); background: none; border: 0; border-top: 1px solid var(--grid);
  padding: 7px 0 2px; cursor: pointer; }
.ftoggle:hover { color: var(--ink); }
.ftoggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.filters.collapsed .fbody { display: none; }

.seg { display: grid; gap: 4px; grid-template-columns: repeat(var(--cols, 4), minmax(0, 1fr)); }
.seg button { font: inherit; font-size: 12.5px; line-height: 1.15; padding: 6px 4px; min-height: 30px;
  color: var(--ink-2); background: var(--surface); border: 1px solid var(--axis); border-radius: 7px; cursor: pointer;
  text-align: center; overflow: hidden; text-overflow: ellipsis; }
.seg button:hover { color: var(--ink); border-color: var(--muted); }
.seg button[aria-pressed="true"] { color: var(--on-accent); background: var(--accent); border-color: var(--accent); font-weight: 600; }
.seg button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
#fMeasure { --cols: 3; } #fGas { --cols: 4; } #fCover { --cols: 3; }
.seg button.dot::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--dot); box-shadow: inset 0 0 0 1px var(--seam); margin-right: 5px; vertical-align: 0; }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px 16px; flex-wrap: wrap; }
.card-head > div:first-child { flex: 1 1 260px; min-width: 0; }
.card-head .detail { flex: 0 1 auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.card-head .detail .flabel { white-space: nowrap; }
.card-head .seg.small { flex-wrap: wrap; justify-content: flex-end; }
#fPeriod { --cols: 5; } #fBiome { --cols: 3; } #fUF { --cols: 7; }
#fUF button:first-child { grid-column: span 2; }
#fCover button:nth-child(-n+3) { font-weight: 600; }
.seg.small { display: flex; } .seg.small button { padding: 5px 10px; border-radius: 999px; }

@media (min-width: 1100px) {
  .layout { display: grid; grid-template-columns: 290px minmax(0, 1fr); gap: 20px; align-items: start; }
  .layout.side-collapsed { grid-template-columns: 40px minmax(0, 1fr); }
  .filters { top: 12px; margin: 0; padding: 4px 14px 8px; background: var(--surface);
    border: 1px solid var(--ring); border-radius: 12px; max-height: calc(100vh - 24px);
    display: flex; flex-direction: column; box-shadow: none !important; }
  .fbody { grid-template-columns: 1fr; gap: 0; max-height: none; flex: 1 1 auto; margin: 0 -14px; padding: 0 14px; }
  .fgroup { padding: 10px 0; border-bottom: 1px solid var(--grid); }
  .fgroup:last-child { border-bottom: 0; }
  #fPeriod { --cols: 4; } #fBiome { --cols: 2; } #fUF { --cols: 6; } #fCover { --cols: 2; }
  .ftoggle { border-top: 1px solid var(--grid); }
  .filters.collapsed { padding: 6px 0; }
  .filters.collapsed .fhead { display: none; }
  .filters.collapsed .ftoggle { border: 0; margin: 0; padding: 10px 0; writing-mode: vertical-rl; min-height: 120px; }
}
@media (max-width: 1099px) { .filters.collapsed .fhead { padding-bottom: 2px; } }

.grid { display: grid; gap: 16px; }
.kpis { grid-template-columns: 1.6fr 1fr 1fr 1fr; margin-bottom: 16px; }
.row2 { grid-template-columns: 2fr 1fr; margin-bottom: 16px; }
.row3 { grid-template-columns: 1fr 1fr; margin-bottom: 16px; }
@media (max-width: 960px) { .kpis { grid-template-columns: 1fr 1fr; } .row2, .row3 { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .kpis { grid-template-columns: 1fr; } }

.card { background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 16px 18px; min-width: 0; }
.card h2 { margin: 0; font-size: 15px; font-weight: 620; }
.card .sub { margin: 2px 0 12px; font-size: 12.5px; color: var(--muted); }
.tile .label { font-size: 12.5px; color: var(--ink-2); }
.tile .value { font-size: 28px; font-weight: 640; margin-top: 6px; line-height: 1.1; }
.tile .value small { font-size: 14px; font-weight: 500; color: var(--ink-2); margin-left: 4px; }
.tile.hero .value { font-size: 52px; letter-spacing: -0.02em; }
.tile .note { font-size: 12.5px; color: var(--muted); margin-top: 6px; }
.delta { font-weight: 600; }
.delta.up { color: var(--up); } .delta.down { color: var(--down); }

.meters { display: grid; gap: 10px; margin-top: 4px; }
.meter { display: grid; grid-template-columns: 52px 1fr 56px; gap: 10px; align-items: center; font-size: 13px; }
.meter .bar { height: 8px; background: var(--accent-weak); border-radius: 4px; overflow: hidden; }
.meter .bar span { display: block; height: 100%; background: var(--accent); border-radius: 4px; }
.meter .fig { text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-2); }

.chart { position: relative; height: 320px; }
.chart.tall { height: 380px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 0 0 10px; padding: 0; list-style: none; font-size: 12.5px; color: var(--ink-2); }
.legend li { display: flex; align-items: center; gap: 6px; }
.legend i, .swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; flex: none; box-shadow: inset 0 0 0 1px var(--seam); }

.split { display: flex; height: 8px; border-radius: 4px; overflow: hidden; gap: 2px; margin: 4px 0 8px; }
.split span { display: block; height: 100%; box-shadow: inset 0 0 0 1px var(--seam); }
.split-legend { display: flex; justify-content: space-between; font-size: 12.5px; color: var(--ink-2); flex-wrap: wrap; gap: 6px; }
.split-legend span { display: inline-flex; align-items: center; gap: 6px; }
.split-legend b { color: var(--ink); font-weight: 600; }

details.table { margin-bottom: 16px; }
details.table summary { cursor: pointer; font-weight: 600; font-size: 14px; }
.table-actions { display: flex; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.table-actions a, .table-actions button { font: inherit; font-size: 13px; color: var(--accent); background: none;
  border: 1px solid var(--axis); border-radius: 8px; padding: 6px 10px; cursor: pointer; text-decoration: none; }
.scroll { overflow: auto; max-height: 460px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--grid); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { position: sticky; top: 0; background: var(--surface); color: var(--ink-2); font-weight: 600; }
td { font-variant-numeric: tabular-nums; }

.matrix-wrap { overflow-x: auto; }
table.matrix { width: 100%; font-size: 12.5px; border-collapse: separate; border-spacing: 2px; }
table.matrix th, table.matrix td { border: 0; padding: 5px 7px; text-align: center; white-space: nowrap; }
table.matrix thead th { position: static; color: var(--ink); font-weight: 650; border-bottom: 1.5px solid var(--ink); }
table.matrix tbody th { text-align: left; font-weight: 600; color: var(--ink); }
table.matrix td { color: var(--muted); border-radius: 3px; font-variant-numeric: tabular-nums; }
table.matrix td.v { color: var(--ink); }
table.matrix .tot { font-weight: 700; color: var(--ink); background: none; }
table.matrix tfoot th, table.matrix tfoot td { border-top: 1.5px solid var(--ink); font-weight: 700; color: var(--ink); }
table.matrix tr.sel th { text-decoration: underline; text-underline-offset: 3px; }
.matrix-note { font-size: 12px; color: var(--muted); margin-top: 8px; }
/* ---- abas ---- */
.tabs { display: flex; gap: 4px; }
.tabs a { font-size: 13px; color: var(--ink-2); text-decoration: none; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--axis); background: var(--surface); }
.tabs a[aria-current="page"] { background: var(--ink); border-color: var(--ink); color: var(--surface); font-weight: 600; }
.hdr-right { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
[hidden] { display: none !important; }

/* ---- página de método ---- */
.mpage { max-width: 1080px; margin: 0 auto; }
.mhero { padding: 8px 0 28px; border-bottom: 1px solid var(--grid); }
.mhero h2 { font-size: 34px; line-height: 1.12; letter-spacing: -0.02em; margin: 0 0 12px; font-weight: 680; max-width: 860px; }
.mhero p { font-size: 16px; color: var(--ink-2); max-width: 760px; margin: 0 0 16px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: 12.5px; padding: 4px 10px; border-radius: 999px; background: var(--accent-weak); color: var(--ink); }
.mtoc { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 18px; font-size: 13px; }
.mtoc a { color: var(--ink-2); text-decoration: none; border-bottom: 1px dotted var(--axis); }
.mtoc a:hover { color: var(--accent); }
.msec { padding: 36px 0 8px; scroll-margin-top: 16px; }
.mnum { font-size: 12.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); font-weight: 700; }
.msec h3 { font-size: 24px; line-height: 1.2; margin: 6px 0 8px; font-weight: 660; letter-spacing: -0.01em; }
.msec > p { color: var(--ink-2); max-width: 780px; margin: 0 0 16px; font-size: 14.5px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.mcard { background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 14px 16px; }
.mcard .k { font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 650; }
.mcard h4 { margin: 4px 0 6px; font-size: 15px; }
.mcard p { margin: 0; font-size: 13px; color: var(--ink-2); }
.mcard code, .msec code { font-size: 12px; background: var(--accent-weak); padding: 1px 5px; border-radius: 4px; word-break: break-all; }
.chain { display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; margin: 8px 0 6px; }
.term { background: var(--surface); border: 1px solid var(--ring); border-radius: 10px; padding: 10px 14px; text-align: center; min-width: 110px; }
.term .v { font-size: 20px; font-weight: 680; line-height: 1.15; }
.term .u { font-size: 11.5px; color: var(--muted); margin-top: 2px; }
.term.hl { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.term.out { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.term.out .u { color: var(--on-accent); opacity: .85; }
.op { align-self: center; font-size: 22px; color: var(--muted); font-weight: 300; padding: 0 2px; }
.callout { border-left: 4px solid var(--accent); background: var(--surface); border-radius: 0 10px 10px 0; padding: 12px 16px; margin: 14px 0; font-size: 13.5px; color: var(--ink-2); max-width: 820px; }
.callout b { color: var(--ink); }
.flow { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 22px; margin-top: 8px; }
.fstep { position: relative; background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 12px 14px; }
.fstep .n { font-size: 11.5px; color: var(--accent); font-weight: 700; }
.fstep h4 { margin: 2px 0 4px; font-size: 14px; }
.fstep p { margin: 0; font-size: 12.5px; color: var(--muted); }
.fstep:not(:last-child)::after { content: "→"; position: absolute; right: -18px; top: 50%; transform: translateY(-50%); color: var(--accent); font-size: 18px; }
table.mtab { border-collapse: separate; border-spacing: 2px; font-size: 12.5px; width: 100%; }
table.mtab th, table.mtab td { padding: 6px 8px; text-align: center; white-space: nowrap; border: 0; }
table.mtab thead th { border-bottom: 1.5px solid var(--ink); color: var(--ink); font-weight: 650; }
table.mtab tbody th { text-align: left; font-weight: 600; }
table.mtab td { border-radius: 3px; font-variant-numeric: tabular-nums; }
.mgrid2 { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
.mgrid2 > * { min-width: 0; }
@media (max-width: 860px) { .mgrid2 { grid-template-columns: 1fr; } .mhero h2 { font-size: 27px; } }
.clist { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 12.5px; color: var(--ink-2); }
.clist span { display: inline-flex; align-items: center; gap: 5px; }
.clist i { width: 9px; height: 9px; border-radius: 50%; box-shadow: inset 0 0 0 1px var(--seam); display: inline-block; }
.calc { background: var(--surface); border: 1px solid var(--ring); border-radius: 14px; padding: 18px; }
.calc .row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
@media (max-width: 860px) { .calc .row { grid-template-columns: 1fr; } }
.calc label.sl { display: grid; grid-template-columns: 110px 1fr 70px; gap: 8px; align-items: center; font-size: 13px; margin: 6px 0; }
.calc input[type=range] { width: 100%; accent-color: var(--accent); }
.calc .sv { text-align: right; font-variant-numeric: tabular-nums; }
.calc .note { font-size: 12.5px; color: var(--muted); }
.gbars { display: grid; gap: 6px; margin-top: 10px; }
.gbar { display: grid; grid-template-columns: 70px 1fr 110px; gap: 10px; align-items: center; font-size: 13px; }
.gbar .t { height: 10px; background: var(--accent-weak); border-radius: 5px; overflow: hidden; }
.gbar .t span { display: block; height: 100%; background: var(--accent); border-radius: 5px; }
.gbar .f { text-align: right; font-variant-numeric: tabular-nums; }
.mfoot { margin: 36px 0 0; padding-top: 14px; border-top: 1px solid var(--grid); font-size: 12.5px; color: var(--muted); display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.mfoot a { color: var(--accent); }
.method { font-size: 13px; color: var(--ink-2); }
.method h2 { color: var(--ink); }
.method ul { margin: 8px 0 0; padding-left: 18px; }
.method li { margin: 3px 0; }
footer { margin-top: 14px; font-size: 12px; color: var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="titles">
    <h1>Monitor de emissões por fogo</h1>
    <p>Emissões mensais de CO₂, CH₄ e N₂O pela queima de vegetação nativa e de áreas agropecuárias no Brasil,
      por bioma, unidade da federação e classe de cobertura.</p>
    <div class="meta" id="meta"></div>
    </div>
    <div class="hdr-right">
      <nav class="tabs" aria-label="Páginas"><a href="#painel" id="tabPainel">Painel</a><a href="#metodo" id="tabMetodo">Método</a></nav>
      <div class="seg small" id="fTheme" role="group" aria-label="Tema"></div>
    </div>
  </header>

  <div id="pagePainel">
  <div class="layout" id="layout">
  <aside class="filters" id="filters" aria-label="Filtros">
    <div class="fhead"><div class="slice" id="slice" aria-live="polite"></div></div>
    <div class="fbody" id="fBody">
      <div class="fgroup"><span class="flabel" id="lMeasure">Medida</span><div class="seg" id="fMeasure" role="group" aria-labelledby="lMeasure"></div></div>
      <div class="fgroup"><span class="flabel" id="lGas">Gás</span><div class="seg" id="fGas" role="group" aria-labelledby="lGas"></div></div>
      <div class="fgroup"><span class="flabel" id="lPeriod">Período</span><div class="seg" id="fPeriod" role="group" aria-labelledby="lPeriod"></div></div>
      <div class="fgroup"><span class="flabel" id="lBiome">Bioma</span><div class="seg" id="fBiome" role="group" aria-labelledby="lBiome"></div></div>
      <div class="fgroup"><span class="flabel" id="lCover">Cobertura</span><div class="seg" id="fCover" role="group" aria-labelledby="lCover"></div></div>
      <div class="fgroup"><span class="flabel" id="lUF">UF</span><div class="seg" id="fUF" role="group" aria-labelledby="lUF"></div></div>
    </div>
    <button type="button" class="ftoggle" id="fToggle" aria-expanded="true" aria-controls="fBody">
      <span class="chev" id="fChev" aria-hidden="true">▴</span><span id="fToggleText">Minimizar filtros</span></button>
  </aside>
  <main class="content">

  <section class="grid kpis" aria-label="Indicadores">
    <div class="card tile hero"><div class="label" id="kEmissLabel">Emissão</div><div class="value" id="kEmiss"></div><div class="note" id="kEmissNote"></div></div>
    <div class="card tile"><div class="label">Área queimada</div><div class="value" id="kArea"></div><div class="note" id="kAreaNote"></div></div>
    <div class="card tile"><div class="label" id="kDensLabel">Densidade</div><div class="value" id="kDens"></div><div class="note" id="kDensNote"></div></div>
    <div class="card tile"><div class="label" id="kLastLabel">Último mês</div><div class="value" id="kLast"></div><div class="note" id="kLastNote"></div></div>
  </section>

  <section class="grid row2">
    <div class="card">
      <div class="card-head">
        <div><h2 id="tMonthly">Emissões por mês</h2><p class="sub" id="sMonthly"></p></div>
        <div class="detail"><span class="flabel" id="lGroup">Detalhar por</span>
          <div class="seg small" id="fGroup" role="group" aria-labelledby="lGroup"></div></div>
      </div>
      <ul class="legend" id="lgMonthly"></ul>
      <div class="chart tall"><canvas id="cMonthly" role="img" aria-label="Série mensal"></canvas></div>
    </div>
    <div class="card">
      <h2>Composição por gás</h2>
      <p class="sub">Participação no CO₂e do recorte (GWP AR5)</p>
      <div class="meters" id="gasMeters"></div>
      <h2 style="margin-top:22px">Natural × antrópico</h2>
      <p class="sub" id="sSplit"></p>
      <div class="split" id="split"></div>
      <div class="split-legend" id="splitLegend"></div>
    </div>
  </section>

  <section class="grid row3">
    <div class="card">
      <h2>Total anual</h2>
      <p class="sub" id="sAnnual"></p>
      <div class="chart"><canvas id="cAnnual" role="img" aria-label="Totais anuais"></canvas></div>
    </div>
    <div class="card">
      <h2>Por classe de cobertura</h2>
      <p class="sub" id="sClass"></p>
      <div class="chart"><canvas id="cClass" role="img" aria-label="Totais por classe"></canvas></div>
    </div>
  </section>

  <section class="card" style="margin-bottom:16px">
    <h2>Por unidade da federação</h2>
    <p class="sub" id="sUF"></p>
    <div class="chart" id="ufBox"><canvas id="cUF" role="img" aria-label="Ranking por UF"></canvas></div>
  </section>

  <section class="card" style="margin-bottom:16px">
    <h2 id="tMxUF">UF × ano</h2>
    <p class="sub" id="sMxUF"></p>
    <div class="matrix-wrap"><table class="matrix" id="mxUF"></table></div>
  </section>
  <section class="card" style="margin-bottom:16px">
    <h2 id="tMxBiome">Bioma × ano</h2>
    <p class="sub" id="sMxBiome"></p>
    <div class="matrix-wrap"><table class="matrix" id="mxBiome"></table></div>
  </section>
  <section class="card" style="margin-bottom:16px">
    <h2 id="tMxCover">Cobertura × ano</h2>
    <p class="sub" id="sMxCover"></p>
    <div class="matrix-wrap"><table class="matrix" id="mxCover"></table></div>
    <p class="matrix-note" id="mxNote"></p>
  </section>

  <details class="card table">
    <summary>Tabela mensal do recorte</summary>
    <div class="table-actions">
      <button type="button" id="dlSlice">Baixar recorte (CSV)</button>
      <a id="dlAll" href="__CSV_HREF__" download>Baixar base completa (CSV)</a>
    </div>
    <div class="scroll"><table id="tbl"><thead></thead><tbody></tbody></table></div>
  </details>

  <section class="card method">
    <h2>Como os números são calculados</h2>
    <p style="margin:4px 0 0"><a href="#metodo" style="color:var(--accent)">Ver a página de método, com o passo a passo e uma calculadora →</a></p>
    <ul>
      <li>Área queimada mensal do monitor MapBiomas Fogo, cruzada com a cobertura MapBiomas Coleção 11 do mesmo ano
        (meses posteriores ao último ano disponível usam a cobertura mais recente) e com os limites de biomas e UFs do IBGE.</li>
      <li>Carbono: mapa de estoques (biomassa aérea, madeira morta e serrapilheira) nas classes naturais; médias por bioma
        nas classes antrópicas. Carbono queimado = carbono × fator de combustão.</li>
      <li>Biomassa queimada = carbono queimado ÷ 0,47. Emissão = biomassa × fator de emissão de cada gás (g/kg de matéria seca).</li>
      <li>CH₄ e N₂O convertidos em CO₂e pelo GWP AR5 (28 e 265). CO₂e total = CO₂ + CH₄ + N₂O.</li>
      <li>Densidade = emissão ÷ área total do território do recorte (bioma, UF ou a interseção dos dois), em t/km².
        Permite comparar recortes de tamanhos diferentes; nos gráficos empilhados, cada parte é a sua contribuição para a densidade do recorte.</li>
      <li>Entram as classes com fatores definidos: formações florestal, savânica e campestre, campo alagado, pastagem,
        mosaico de usos e agricultura.</li>
    </ul>
    <footer id="foot"></footer>
  </section>
  </main>
  </div>
  </div>

  <article class="mpage" id="pageMetodo" hidden>
    <div class="mhero" id="mtopo">
      <div class="mnum">metodologia</div>
      <h2>Emissões do fogo no Brasil, estimadas mês a mês e pixel a pixel.</h2>
      <p>O monitor combina o mapeamento mensal de áreas queimadas com mapas de uso e cobertura da terra e de estoques de carbono
        para estimar quanto CO₂, CH₄ e N₂O o fogo lança na atmosfera a cada mês, com resolução de 30 metros e recortes por bioma,
        estado e tipo de vegetação.</p>
      <div class="chips"><span class="chip">área queimada mensal</span><span class="chip">cobertura MapBiomas</span>
        <span class="chip">estoques de carbono</span><span class="chip">fator de combustão</span><span class="chip">CO₂ · CH₄ · N₂O</span><span class="chip">IPCC AR5</span></div>
      <nav class="mtoc" aria-label="Seções da metodologia">
        <a href="#m-fontes">01 dados</a><a href="#m-pixel">02 pixel queimado</a><a href="#m-carbono">03 carbono queimado</a>
        <a href="#m-biomassa">04 biomassa</a><a href="#m-gases">05 gases</a><a href="#m-calc">06 simule</a>
        <a href="#m-tabelas">07 estatísticas</a><a href="#m-fluxo">08 processo</a><a href="#m-limites">09 escopo</a>
      </nav>
    </div>

    <section class="msec" id="m-fontes">
      <div class="mnum">01 / dados</div>
      <h3>Quatro bases públicas e consolidadas.</h3>
      <p>Todas são processadas em resolução de 30 metros na plataforma Google Earth Engine, com cobertura nacional e atualização contínua.</p>
      <div class="cards">
        <div class="mcard"><div class="k">quando e onde queimou</div><h4>Área queimada mensal</h4><p>Monitor mensal do MapBiomas Fogo, disponível desde janeiro de 2019.</p></div>
        <div class="mcard"><div class="k">o que queimou</div><h4>Uso e cobertura da terra</h4><p>MapBiomas Coleção 11, com a classe de cada pixel em cada ano.</p></div>
        <div class="mcard"><div class="k">quanto carbono havia</div><h4>Estoques de carbono</h4><p>Mapa de biomassa aérea, madeira morta e serrapilheira, em toneladas de carbono por hectare.</p></div>
        <div class="mcard"><div class="k">onde somar</div><h4>Limites territoriais</h4><p>Biomas e unidades da federação do IBGE, usados para os recortes e as estatísticas.</p></div>
      </div>
    </section>

    <section class="msec" id="m-pixel">
      <div class="mnum">02 / pixel queimado</div>
      <h3>Cada pixel queimado é identificado pela sua cobertura.</h3>
      <p>Para cada mês, identifica-se onde houve fogo e qual era a cobertura do solo naquele ano. As classes do MapBiomas são agrupadas
        em seis categorias de vegetação, cada uma com parâmetros próprios de queima.</p>
      <div class="chain"><div class="term"><div class="v">fogo no mês</div><div class="u">MapBiomas Fogo</div></div><div class="op">+</div>
        <div class="term"><div class="v">cobertura do ano</div><div class="u">MapBiomas</div></div><div class="op">+</div>
        <div class="term"><div class="v">bioma</div><div class="u">IBGE</div></div><div class="op">→</div>
        <div class="term out"><div class="v">categoria de queima</div><div class="u">parâmetros por bioma</div></div></div>
      <div class="cards" id="mClasses" style="margin-top:14px"></div>
    </section>

    <section class="msec" id="m-carbono">
      <div class="mnum">03 / carbono queimado</div>
      <h3>O carbono disponível para queimar depende da vegetação.</h3>
      <p>Nas formações nativas, o carbono vem do mapa de estoques, pixel a pixel: em florestas, consideram-se a madeira morta e a serrapilheira;
        em savanas, parte da biomassa aérea somada a esses resíduos; em campos, toda a biomassa aérea e os resíduos. Em pastagens e agricultura,
        usa-se o estoque médio de cada bioma. O fator de combustão indica a fração desse carbono efetivamente consumida pelo fogo.</p>
      <div class="chain"><div class="term"><div class="v">estoque de carbono</div><div class="u">t C/ha</div></div><div class="op">×</div>
        <div class="term"><div class="v">fator de combustão</div><div class="u">fração consumida</div></div><div class="op">=</div>
        <div class="term out"><div class="v">carbono queimado</div><div class="u">t C/ha</div></div></div>
      <div class="mgrid2" style="margin-top:14px">
        <div class="mcard"><div class="k">compartimentos de carbono considerados</div><table class="mtab" id="mPools"></table></div>
        <div class="mcard"><div class="k">fator de combustão por bioma</div><div style="overflow-x:auto"><table class="mtab" id="mCf"></table></div></div>
      </div>
    </section>

    <section class="msec" id="m-biomassa">
      <div class="mnum">04 / biomassa</div>
      <h3>Do carbono à biomassa queimada.</h3>
      <p>Os fatores de emissão são expressos por quilo de matéria seca. Como cerca de 47% da matéria seca vegetal é carbono,
        a biomassa queimada é obtida dividindo-se o carbono queimado por 0,47.</p>
      <div class="chain"><div class="term"><div class="v">carbono queimado</div><div class="u">t C/ha</div></div><div class="op">÷</div>
        <div class="term hl"><div class="v">0,47</div><div class="u">fração de carbono</div></div><div class="op">=</div>
        <div class="term out"><div class="v">biomassa queimada</div><div class="u">t de matéria seca/ha</div></div></div>
    </section>

    <section class="msec" id="m-gases">
      <div class="mnum">05 / gases</div>
      <h3>Três gases de efeito estufa, em CO₂ equivalente.</h3>
      <p>Cada categoria tem fatores de emissão específicos para CO₂, CH₄ e N₂O, em gramas por quilo de matéria seca, com base no Inventário Nacional
        e no IPCC. CH₄ e N₂O são convertidos em CO₂ equivalente pelo potencial de aquecimento global do IPCC AR5.</p>
      <div class="chain"><div class="term"><div class="v">biomassa queimada</div><div class="u">kg de matéria seca</div></div><div class="op">×</div>
        <div class="term"><div class="v">fator de emissão</div><div class="u">g de gás / kg</div></div><div class="op">×</div>
        <div class="term"><div class="v">GWP</div><div class="u">CH₄ 28 · N₂O 265</div></div><div class="op">=</div>
        <div class="term out"><div class="v">emissão</div><div class="u">t CO₂e</div></div></div>
      <div class="mcard" style="margin-top:14px"><div class="k">fatores de emissão (g por kg de matéria seca)</div><div style="overflow-x:auto"><table class="mtab" id="mEf"></table></div></div>
    </section>

    <section class="msec" id="m-calc">
      <div class="mnum">06 / simule</div>
      <h3>Simule a estimativa para um hectare.</h3>
      <p>Escolha o bioma e a categoria de vegetação. Nas formações nativas, ajuste os estoques de carbono para ver como cada etapa influencia o resultado.</p>
      <div class="calc">
        <div class="row">
          <div><div class="flabel">Bioma</div><div class="seg" id="cBioma" style="--cols:3"></div></div>
          <div><div class="flabel">Categoria</div><div class="seg" id="cCat" style="--cols:2"></div></div>
        </div>
        <div id="cPools"></div>
        <div class="chain" id="cChain" style="margin-top:12px"></div>
        <div class="gbars" id="cGas"></div>
        <p class="note" id="cNote"></p>
      </div>
    </section>

    <section class="msec" id="m-tabelas">
      <div class="mnum">07 / estatísticas</div>
      <h3>Do mapa às estatísticas por território.</h3>
      <p>As estimativas por pixel são convertidas em toneladas considerando a área real de cada pixel e somadas por bioma, estado e classe de cobertura,
        mês a mês. A densidade de emissão, em toneladas por km² de território, permite comparar regiões de tamanhos diferentes.</p>
      <div class="chain"><div class="term"><div class="v">emissão por hectare</div><div class="u">em cada pixel</div></div><div class="op">×</div>
        <div class="term"><div class="v">área do pixel</div><div class="u">~0,09 ha</div></div><div class="op">Σ</div>
        <div class="term"><div class="v">bioma × estado × classe</div><div class="u">por mês</div></div><div class="op">=</div>
        <div class="term out"><div class="v">t CO₂e</div><div class="u">por recorte</div></div></div>
      <div class="chain"><div class="term"><div class="v">t CO₂e</div><div class="u">do recorte</div></div><div class="op">÷</div>
        <div class="term"><div class="v">área do território</div><div class="u">km²</div></div><div class="op">=</div>
        <div class="term out"><div class="v">densidade</div><div class="u">t CO₂e/km²</div></div></div>
    </section>

    <section class="msec" id="m-fluxo">
      <div class="mnum">08 / processo</div>
      <h3>Um processo reprodutível, do satélite ao painel.</h3>
      <div class="flow">
        <div class="fstep"><div class="n">1</div><h4>Dados de entrada</h4><p>fogo mensal, cobertura, carbono e limites</p></div>
        <div class="fstep"><div class="n">2</div><h4>Mapas de emissão</h4><p>um por mês, três gases, 30 m</p></div>
        <div class="fstep"><div class="n">3</div><h4>Estatísticas</h4><p>por bioma, estado e classe</p></div>
        <div class="fstep"><div class="n">4</div><h4>Base consolidada</h4><p>série completa, aberta para download</p></div>
        <div class="fstep"><div class="n">5</div><h4>Painel</h4><p>consulta, filtros e matrizes</p></div>
      </div>
    </section>

    <section class="msec" id="m-limites">
      <div class="mnum">09 / escopo e premissas</div>
      <h3>O que a estimativa cobre.</h3>
      <div class="cards">
        <div class="mcard"><h4>Vegetação e agropecuária</h4><p>A estimativa cobre a queima de formações nativas, pastagens e lavouras. Áreas urbanas, corpos d'água e áreas não vegetadas não entram.</p></div>
        <div class="mcard"><h4>Estoques de referência</h4><p>Os estoques de carbono das formações nativas têm como referência o mapa de 2019.</p></div>
        <div class="mcard"><h4>Cobertura mais recente</h4><p id="mLastCov"></p></div>
        <div class="mcard"><h4>Áreas agropecuárias</h4><p>Pastagens e lavouras usam o estoque médio de carbono de cada bioma.</p></div>
      </div>
    </section>

    <div class="mfoot"><span>MapBiomas Fogo · IPAM</span><a href="#mtopo">voltar ao topo ↑</a></div>
  </article>
</div>

<script>
const DATA = __DATA__;
const F = DATA.facts, N = F.m.length;
const MONTHS = DATA.months, BIOMES = DATA.biomes, NB = BIOMES.length, NM = MONTHS.length;
const MON = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
const mLabel = ym => MON[+ym.slice(5) - 1] + '/' + ym.slice(2, 4);
const mLong = ym => MON[+ym.slice(5) - 1] + ' de ' + ym.slice(0, 4);
const YEARS = [...new Set(MONTHS.map(m => m.slice(0, 4)))];
const LAST = MONTHS[NM - 1];
const LAST_YEAR_PARTIAL = LAST.slice(5) !== '12';
const GAS = {
  total: { name: 'CO₂e total', unit: 't CO₂e' },
  co2: { name: 'CO₂', unit: 't CO₂' },
  ch4: { name: 'CH₄', unit: 't CO₂e' },
  n2o: { name: 'N₂O', unit: 't CO₂e' },
};
const $ = id => document.getElementById(id);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const biomeColor = i => css('--s' + (i + 1));

// ---------- formatação ----------
const NF = {};
const nf = d => NF[d] || (NF[d] = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: d }));
function fmtT(t) {
  const a = Math.abs(t);
  if (a >= 1e6) return [nf(a >= 1e8 ? 0 : a >= 1e7 ? 1 : 2).format(t / 1e6), 'Mt'];
  if (a >= 1e3) return [nf(a >= 1e5 ? 0 : 1).format(t / 1e3), 'mil t'];
  return [nf(0).format(t), 't'];
}
function fmtHa(ha) {
  const a = Math.abs(ha);
  if (a >= 1e6) return [nf(a >= 1e7 ? 1 : 2).format(ha / 1e6), 'milhões de ha'];
  if (a >= 1e3) return [nf(a >= 1e5 ? 0 : 1).format(ha / 1e3), 'mil ha'];
  return [nf(0).format(ha), 'ha'];
}
const axisTick = v => {
  const a = Math.abs(v);
  if (a >= 1e6) return nf(1).format(v / 1e6) + ' mi';
  if (a >= 1e3) return nf(0).format(v / 1e3) + ' mil';
  return nf(a < 10 ? 1 : 0).format(v);
};
const fullVal = v => v === null || v === undefined ? '—' : nf(S.measure === 'dens' ? 2 : 0).format(v);
function setValue(el, num, unit) {
  el.textContent = num;
  const s = document.createElement('small'); s.textContent = unit; el.appendChild(s);
}

// ---------- filtros (botões) ----------
const S = { measure: 'emiss', gas: 'total', group: 'cover', cover: 'all', period: 'all', biome: 'all', uf: 'all', theme: 'light' };
const COVER = DATA.cover, NC = COVER.length;
const coverIdx = {}; COVER.forEach(([name], k) => { coverIdx[name] = k; });
const OTHER = coverIdx['Outras classes'];
const CLASS_COVER = DATA.classes.map(c => coverIdx[c['Nível 1_1']] ?? OTHER);
const coverColor = k => COVER[k][1];
const IS_NAT = DATA.classes.map(c => c['Nível 0'] === 'Natural');
// filtro de cobertura: all | nat | ant | g<k>
function coverPass(ci) {
  const v = S.cover;
  if (v === 'all') return true;
  if (v === 'nat') return IS_NAT[ci];
  if (v === 'ant') return !IS_NAT[ci];
  return CLASS_COVER[ci] === +v.slice(1);
}
function coverLabel() {
  const v = S.cover;
  return v === 'all' ? '' : v === 'nat' ? 'vegetação nativa' : v === 'ant' ? 'agropecuária' : COVER[+v.slice(1)][0];
}
// classes detalhadas (Nível 4)
const N4 = [...new Set(DATA.classes.map(c => c['Nível 4']))];
const CLASS_N4 = DATA.classes.map(c => N4.indexOf(c['Nível 4']));
const N4_COLOR = N4.map(n => DATA.classes.find(c => c['Nível 4'] === n).color);
// modos de detalhamento da série mensal: chave por linha de fato, rótulos e cores
const FOLD = 7;
const DETAIL = {
  cover: { n: () => NC, key: i => CLASS_COVER[F.c[i]], label: k => COVER[k][0], color: k => coverColor(k) },
  n0: { n: () => 2, key: i => IS_NAT[F.c[i]] ? 0 : 1, label: k => ['Vegetação nativa', 'Agropecuária'][k],
        color: k => css(k === 0 ? '--nat' : '--ant') },
  n4: { n: () => N4.length, key: i => CLASS_N4[F.c[i]], label: k => N4[k], color: k => N4_COLOR[k], fold: 'Outras classes' },
  biome: { n: () => NB, key: i => F.b[i], label: k => BIOMES[k], color: k => biomeColor(k) },
  uf: { n: () => DATA.ufs.length, key: i => F.u[i], label: k => DATA.ufs[k].sigla, color: null, fold: 'Outras UFs' },
};
function seg(id, key, items, after) {
  const el = $(id); el.textContent = '';
  items.forEach(([value, text, title, dotColor]) => {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.textContent = text;
    if (title) btn.title = title;
    if (dotColor) { btn.classList.add('dot'); btn.style.setProperty('--dot', dotColor); }
    btn.setAttribute('aria-pressed', String(S[key] === value));
    btn.addEventListener('click', () => {
      if (S[key] === value) return;
      S[key] = value; seg(id, key, items, after); (after || renderAll)();
    });
    el.appendChild(btn);
  });
}
const ufsByBiome = BIOMES.map(() => new Set());
for (let i = 0; i < N; i++) ufsByBiome[F.b[i]].add(F.u[i]);
function fillUF() {
  const allowed = S.biome === 'all' ? null : ufsByBiome[+S.biome];
  if (S.uf !== 'all' && allowed && !allowed.has(+S.uf)) S.uf = 'all';
  const items = [['all', 'Todas']];
  DATA.ufs.forEach((u, i) => { if (!allowed || allowed.has(i)) items.push([String(i), u.sigla, u.nome]); });
  seg('fUF', 'uf', items);
}
seg('fMeasure', 'measure', [['emiss', 'Emissão'], ['dens', 'Densidade', 'Emissão ÷ área do território (t/km²)'], ['area', 'Área queim.', 'Área queimada']]);
seg('fGroup', 'group', [['cover', 'Cobertura'], ['n0', 'Nativa × agro', 'Vegetação nativa × agropecuária'],
  ['n4', 'Classe', 'Classe detalhada (MapBiomas)'], ['biome', 'Bioma'], ['uf', 'UF']]);
(function () {
  const items = [['all', 'Todas'], ['nat', 'Nativa', 'Vegetação nativa'], ['ant', 'Agropec.', 'Agropecuária']]
    .concat(COVER.map(([name, color], k) => ['g' + k, DATA.cover_short[name] || name, name, color]));
  seg('fCover', 'cover', items);
})();
seg('fTheme', 'theme', [['light', 'Claro'], ['dark', 'Escuro']], () => {
  document.documentElement.setAttribute('data-theme', S.theme); renderAll(); buildMethod();
});
seg('fGas', 'gas', [['total', 'CO₂e', 'CO₂e total (CO₂ + CH₄ + N₂O)'], ['co2', 'CO₂'], ['ch4', 'CH₄', 'CH₄ em CO₂e'], ['n2o', 'N₂O', 'N₂O em CO₂e']]);
seg('fPeriod', 'period', [['all', 'Tudo'], ['l12', '12m', 'Últimos 12 meses']].concat([...YEARS].reverse().map(y =>
  ['y' + y, y + (y === LAST.slice(0, 4) && LAST_YEAR_PARTIAL ? '*' : ''),
   y === LAST.slice(0, 4) && LAST_YEAR_PARTIAL ? y + ' até ' + MON[+LAST.slice(5) - 1] : ''])));
seg('fBiome', 'biome', [['all', 'Todos']].concat(BIOMES.map((b, i) => [String(i), b])), () => { fillUF(); renderAll(); });
fillUF();

// área do território (km²) por bioma × UF
const TERR = BIOMES.map(() => new Float64Array(DATA.ufs.length));
DATA.territory.forEach(([b, u, km2]) => { TERR[b][u] = km2; });
function territory(bSel, uSel) {
  let t = 0;
  for (let b = 0; b < NB; b++) { if (bSel >= 0 && b !== bSel) continue;
    for (let u = 0; u < DATA.ufs.length; u++) { if (uSel >= 0 && u !== uSel) continue; t += TERR[b][u]; } }
  return t;
}

function monthRange() {
  const v = S.period;
  if (v === 'all') return [0, NM - 1];
  if (v === 'l12') return [Math.max(0, NM - 12), NM - 1];
  const y = v.slice(1);
  const idx = MONTHS.map((m, i) => m.startsWith(y) ? i : -1).filter(i => i >= 0);
  return [idx[0], idx[idx.length - 1]];
}

// ---------- agregação ----------
function aggregate() {
  const [m0, m1] = monthRange();
  const bSel = S.biome === 'all' ? -1 : +S.biome;
  const uSel = S.uf === 'all' ? -1 : +S.uf;
  const g = S.gas;
  const R = {
    m0, m1,
    mA: new Float64Array(NM * NB), mE: new Float64Array(NM * NB),   // todos os meses, por bioma
    mG: new Float64Array(NM * 3),                                     // todos os meses, por gás (tabela)
    mCA: new Float64Array(NM * NC), mCE: new Float64Array(NM * NC),   // todos os meses, por cobertura
    nD: DETAIL[S.group].n(),
    uA: new Float64Array(DATA.ufs.length), uE: new Float64Array(DATA.ufs.length),
    cA: {}, cE: {}, nat: { A: 0, E: 0 }, ant: { A: 0, E: 0 },
    gas: [0, 0, 0], A: 0, E: 0,
    T: territory(bSel, uSel),
    uT: DATA.ufs.map((_, u) => territory(bSel, u)),
  };
  R.dA = new Float64Array(NM * R.nD); R.dE = new Float64Array(NM * R.nD);
  const dKey = DETAIL[S.group].key;
  for (let i = 0; i < N; i++) {
    const b = F.b[i], u = F.u[i];
    if (bSel >= 0 && b !== bSel) continue;
    if (uSel >= 0 && u !== uSel) continue;
    if (!coverPass(F.c[i])) continue;
    const m = F.m[i], a = F.a[i], c2 = F.co2[i], c4 = F.ch4[i], n2 = F.n2o[i];
    const e = g === 'total' ? c2 + c4 + n2 : g === 'co2' ? c2 : g === 'ch4' ? c4 : n2;
    R.mA[m * NB + b] += a; R.mE[m * NB + b] += e;
    R.mG[m * 3] += c2; R.mG[m * 3 + 1] += c4; R.mG[m * 3 + 2] += n2;
    const ck = CLASS_COVER[F.c[i]]; R.mCA[m * NC + ck] += a; R.mCE[m * NC + ck] += e;
    const dk = dKey(i); R.dA[m * R.nD + dk] += a; R.dE[m * R.nD + dk] += e;
    if (m < m0 || m > m1) continue;
    R.A += a; R.E += e;
    R.gas[0] += c2; R.gas[1] += c4; R.gas[2] += n2;
    R.uA[u] += a; R.uE[u] += e;
    const cl = DATA.classes[F.c[i]], k = cl['Nível 1_1'];
    R.cA[k] = (R.cA[k] || 0) + a; R.cE[k] = (R.cE[k] || 0) + e;
    const side = cl['Nível 0'] === 'Natural' ? R.nat : R.ant;
    side.A += a; side.E += e;
  }
  return R;
}
// densidade usa a área do território (T); nas partes empilhadas, T é o do recorte inteiro
function measureOf(A, E, T) {
  const ms = S.measure;
  if (ms === 'area') return A;
  if (ms === 'emiss') return E;
  return T > 0 ? E / T : null;
}
function measureUnit() {
  const ms = S.measure, g = GAS[S.gas];
  return ms === 'area' ? 'ha' : ms === 'emiss' ? g.unit : g.unit + '/km²';
}
function measureName() {
  const ms = S.measure, g = GAS[S.gas];
  return ms === 'area' ? 'Área queimada' : ms === 'emiss' ? 'Emissão de ' + g.name : 'Densidade de ' + g.name;
}
function sliceText() {
  const b = S.biome === 'all' ? 'Brasil' : BIOMES[+S.biome];
  const u = S.uf === 'all' ? '' : ' · ' + DATA.ufs[+S.uf].sigla;
  const [m0, m1] = monthRange();
  const c = coverLabel();
  return b + u + (c ? ' · ' + c : '') + ' · ' + mLabel(MONTHS[m0]) + ' a ' + mLabel(MONTHS[m1]);
}

// ---------- gráficos ----------
Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.animation = false;

function themeChart(ch) {
  const grid = css('--grid'), muted = css('--muted'), axis = css('--axis');
  Object.values(ch.options.scales).forEach(s => {
    s.grid = Object.assign(s.grid || {}, { color: grid, drawTicks: false });
    s.border = { color: axis };
    s.ticks = Object.assign(s.ticks || {}, { color: muted, padding: 6 });
  });
  const t = ch.options.plugins.tooltip;
  Object.assign(t, { backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink'),
    borderColor: css('--axis'), borderWidth: 1, padding: 10, boxPadding: 4, usePointStyle: true });
}
function makeBar(canvas, horizontal) {
  return new Chart(canvas, {
    type: 'bar',
    data: { labels: [], datasets: [] },
    options: {
      indexAxis: horizontal ? 'y' : 'x',
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false, axis: horizontal ? 'y' : 'x' },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => {
          const v = c.parsed[horizontal ? 'x' : 'y'];
          const many = c.chart.data.datasets.length > 1;
          return ' ' + (many ? c.dataset.label + ': ' : '') + fullVal(v) + ' ' + measureUnit();
        } } },
      },
      scales: horizontal
        ? { x: { beginAtZero: true, ticks: { callback: axisTick, maxTicksLimit: 6 } }, y: { grid: { display: false } } }
        : { x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
            y: { stacked: true, beginAtZero: true, ticks: { callback: axisTick, maxTicksLimit: 6 } } },
    },
  });
}
const cMonthly = makeBar($('cMonthly'), false);
const cAnnual = makeBar($('cAnnual'), false);
const cClass = makeBar($('cClass'), true);
const cUF = makeBar($('cUF'), true);

// barra: <= 24px, ponta arredondada (4px) e base reta; segmentos empilhados separados por 2px da cor do fundo
function barStyle(color, opts) {
  const o = opts || {};
  return {
    backgroundColor: color, hoverBackgroundColor: color, maxBarThickness: 24,
    borderSkipped: 'start', borderRadius: o.flat ? 0 : 4,
    borderColor: o.seam ? css('--seam') : css('--surface'), borderWidth: o.seam ? 1 : o.stacked ? { top: 2 } : 0,
  };
}
function legend(el, items) {
  el.textContent = '';
  items.forEach(([name, color]) => {
    const li = document.createElement('li'); const sw = document.createElement('i');
    sw.style.background = color; li.append(sw, document.createTextNode(name)); el.appendChild(li);
  });
}
function monthSum(R, m) {
  let a = 0, e = 0;
  for (let b = 0; b < NB; b++) { a += R.mA[m * NB + b]; e += R.mE[m * NB + b]; }
  return [a, e];
}

function renderMonthly(R) {
  const ms = S.measure, D = DETAIL[S.group], nD = R.nD;
  const idx = []; for (let m = R.m0; m <= R.m1; m++) idx.push(m);
  cMonthly.data.labels = idx.map(m => mLabel(MONTHS[m]));
  const tot = new Float64Array(nD);
  idx.forEach(m => { for (let k = 0; k < nD; k++) tot[k] += R.dA[m * nD + k] + R.dE[m * nD + k]; });
  let keys = [...Array(nD).keys()].filter(k => tot[k] > 0);
  let rest = [];
  if (D.fold) {
    keys.sort((x, y) => tot[y] - tot[x]);
    if (keys.length > FOLD + 1) { rest = keys.slice(FOLD); keys = keys.slice(0, FOLD); }
  }
  const pal = ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7'];
  const colorOf = (k, r) => D.color ? D.color(k) : css(pal[r]) || css('--accent');
  const series = keys.map((k, r) => ({ label: D.label(k), color: colorOf(k, r),
    A: m => R.dA[m * nD + k], E: m => R.dE[m * nD + k] }));
  if (rest.length) series.push({ label: D.fold + ' (' + rest.length + ')', color: '#9c8f80',
    A: m => rest.reduce((s, k) => s + R.dA[m * nD + k], 0), E: m => rest.reduce((s, k) => s + R.dE[m * nD + k], 0) });
  const seam = !!D.color || true;
  cMonthly.data.datasets = series.map(sr => ({
    label: sr.label, data: idx.map(m => measureOf(sr.A(m), sr.E(m), R.T)),
    ...barStyle(sr.color, { seam, flat: true }),
  }));
  cMonthly.options.scales.x.stacked = cMonthly.options.scales.y.stacked = true;
  legend($('lgMonthly'), series.map(sr => [sr.label, sr.color]));
  const how = { cover: 'cobertura do solo (cores MapBiomas)', n0: 'vegetação nativa × agropecuária',
    n4: 'classe detalhada (cores MapBiomas; ' + FOLD + ' maiores no período)', biome: 'bioma',
    uf: 'UF (' + FOLD + ' maiores no período)' }[S.group];
  $('sMonthly').textContent = measureName() + ' (' + measureUnit() + '), empilhado por ' + how;
  cMonthly.options.plugins.tooltip.callbacks.title = items => mLong(MONTHS[idx[items[0].dataIndex]]);
  cMonthly.options.plugins.tooltip.callbacks.footer = items => {
    if (items.length < 2) return '';
    const t = items.reduce((s, it) => s + (it.parsed.y || 0), 0);
    return 'Total: ' + fullVal(t) + ' ' + measureUnit();
  };
  cMonthly.options.plugins.tooltip.itemSort = (x, y) => (y.parsed.y || 0) - (x.parsed.y || 0);
  cMonthly.options.plugins.tooltip.filter = it => (it.parsed.y || 0) > 0;
  $('tMonthly').textContent = ms === 'area' ? 'Área queimada por mês' : ms === 'dens' ? 'Densidade de emissão por mês' : 'Emissões por mês';
  themeChart(cMonthly); cMonthly.update();
}

function renderAnnual(R) {
  const bSel = S.biome === 'all' ? -1 : +S.biome;
  const vals = YEARS.map(y => {
    let a = 0, e = 0;
    MONTHS.forEach((m, i) => { if (m.startsWith(y)) { const [ma, me] = monthSum(R, i); a += ma; e += me; } });
    return measureOf(a, e, R.T);
  });
  cAnnual.data.labels = YEARS.map(y => y === LAST.slice(0, 4) && LAST_YEAR_PARTIAL ? y + '*' : y);
  cAnnual.data.datasets = [{ label: measureName(), data: vals, ...barStyle(bSel >= 0 ? biomeColor(bSel) : css('--accent')) }];
  cAnnual.options.scales.x.stacked = cAnnual.options.scales.y.stacked = false;
  $('sAnnual').textContent = measureName() + ' (' + measureUnit() + '), todos os anos'
    + (LAST_YEAR_PARTIAL ? ' · *' + LAST.slice(0, 4) + ' até ' + MON[+LAST.slice(5) - 1] : '');
  themeChart(cAnnual); cAnnual.update();
}

function renderRanked(chart, labels, A, E, T, subEl, what, note, colorOf) {
  const rows = labels.map((l, i) => ({ l, v: measureOf(A[i], E[i], T[i]), a: A[i] }))
    .filter(r => r.a > 0 && r.v !== null).sort((x, y) => y.v - x.v);
  chart.data.labels = rows.map(r => r.l);
  chart.data.datasets = [{ label: measureName(), data: rows.map(r => r.v), ...barStyle(css('--accent')) }];
  if (colorOf) Object.assign(chart.data.datasets[0], {
    backgroundColor: rows.map(r => colorOf(r.l)), hoverBackgroundColor: rows.map(r => colorOf(r.l)),
    borderColor: css('--seam'), borderWidth: 1, borderSkipped: false });
  subEl.textContent = measureName() + ' (' + measureUnit() + ') ' + what + (S.measure === 'dens' && note ? ' · ' + note : '');
  themeChart(chart); chart.update();
  return rows.length;
}
function renderClass(R) {
  const labels = Object.keys(R.cA);
  renderRanked(cClass, labels, labels.map(k => R.cA[k]), labels.map(k => R.cE[k]), labels.map(() => R.T), $('sClass'),
    'por classe', 'contribuição de cada classe para a densidade do recorte',
    l => coverColor(coverIdx[l] ?? OTHER));
}
function renderUF(R) {
  const n = renderRanked(cUF, DATA.ufs.map(u => u.sigla), Array.from(R.uA), Array.from(R.uE), R.uT, $('sUF'), 'por UF',
    'emissão de cada UF ÷ área da UF' + (S.biome === 'all' ? '' : ' no bioma'));
  $('ufBox').style.height = Math.max(140, n * 24 + 40) + 'px';
}

function renderKPIs(R) {
  const g = GAS[S.gas];
  $('kEmissLabel').textContent = 'Emissão de ' + g.name;
  const [ev, eu] = fmtT(R.E);
  setValue($('kEmiss'), ev, eu + (S.gas === 'co2' ? ' CO₂' : ' CO₂e'));
  $('kEmissNote').textContent = sliceText();
  setValue($('kArea'), ...fmtHa(R.A));
  $('kAreaNote').textContent = nf(0).format(R.A / 100) + ' km²';
  $('kDensLabel').textContent = 'Densidade de ' + g.name;
  setValue($('kDens'), R.T > 0 ? new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(R.E / R.T) : '—',
    't/km²');
  $('kDensNote').textContent = 'emissão ÷ ' + nf(0).format(R.T) + ' km² de território';

  // último mês × mesmo mês do ano anterior (no mesmo bioma/UF; não depende do período)
  const prevYm = (+LAST.slice(0, 4) - 1) + LAST.slice(4), iP = MONTHS.indexOf(prevYm);
  const eL = monthSum(R, NM - 1)[1], eP = iP >= 0 ? monthSum(R, iP)[1] : 0;
  $('kLastLabel').textContent = 'Emissão em ' + mLong(LAST);
  setValue($('kLast'), ...fmtT(eL));
  const note = $('kLastNote'); note.textContent = '';
  if (eP > 0) {
    const d = (eL / eP - 1) * 100;
    const sp = document.createElement('span'); sp.className = 'delta ' + (d >= 0 ? 'up' : 'down');
    sp.textContent = (d >= 0 ? '▲ +' : '▼ ') + nf(0).format(d) + '%';
    note.append(sp, document.createTextNode(' vs ' + mLabel(prevYm) + ' (' + fmtT(eP).join(' ') + ')'));
  } else note.textContent = 'sem base de comparação';
}

function renderSide(R) {
  const tot = R.gas[0] + R.gas[1] + R.gas[2];
  const box = $('gasMeters'); box.textContent = '';
  [['CO₂', R.gas[0]], ['CH₄', R.gas[1]], ['N₂O', R.gas[2]]].forEach(([n, v]) => {
    const share = tot > 0 ? v / tot : 0;
    const row = document.createElement('div'); row.className = 'meter';
    row.title = n + ': ' + fmtT(v).join(' ') + ' CO₂e';
    const name = document.createElement('span'); name.textContent = n;
    const bar = document.createElement('div'); bar.className = 'bar';
    const fill = document.createElement('span'); fill.style.width = (share * 100).toFixed(2) + '%'; bar.appendChild(fill);
    const fig = document.createElement('span'); fig.className = 'fig'; fig.textContent = nf(1).format(share * 100) + '%';
    row.append(name, bar, fig); box.appendChild(row);
  });

  const useArea = S.measure === 'area';
  const nv = useArea ? R.nat.A : R.nat.E, av = useArea ? R.ant.A : R.ant.E, t = nv + av;
  $('sSplit').textContent = (useArea ? 'Área queimada' : 'Emissão de ' + GAS[S.gas].name) + ' por tipo de cobertura';
  const parts = [['Vegetação nativa', nv, css('--nat')], ['Agropecuária', av, css('--ant')]];
  const split = $('split'); split.textContent = '';
  parts.forEach(([n, v, c]) => { if (v > 0) { const s = document.createElement('span'); s.style.flex = String(v); s.style.background = c; s.title = n; split.appendChild(s); } });
  const lg = $('splitLegend'); lg.textContent = '';
  parts.forEach(([n, v, c]) => {
    const d = document.createElement('span'); const sw = document.createElement('i'); sw.className = 'swatch'; sw.style.background = c;
    const b = document.createElement('b'); b.textContent = t > 0 ? nf(0).format(v / t * 100) + '%' : '—';
    d.append(sw, document.createTextNode(n + ' '), b); lg.appendChild(d);
  });
}

// ---------- matrizes (linhas × ano) ----------
const NY = YEARS.length, NU = DATA.ufs.length;
const YEAR_OF = MONTHS.map(m => YEARS.indexOf(m.slice(0, 4)));
function aggregateYears() {
  // ignora o período (colunas = anos); respeita bioma, UF e gás
  const bSel = S.biome === 'all' ? -1 : +S.biome, uSel = S.uf === 'all' ? -1 : +S.uf, g = S.gas;
  const Z = n => ({ A: new Float64Array(n * NY), E: new Float64Array(n * NY) });
  const M = { uf: Z(NU), biome: Z(NB), cover: Z(NC) };
  for (let i = 0; i < N; i++) {
    const b = F.b[i], u = F.u[i];
    const inB = bSel < 0 || b === bSel, inU = uSel < 0 || u === uSel;
    if (!inB || !coverPass(F.c[i])) continue;  // todas as matrizes respeitam bioma e cobertura
    const y = YEAR_OF[F.m[i]], a = F.a[i];
    const e = g === 'total' ? F.co2[i] + F.ch4[i] + F.n2o[i] : F[g][i];
    M.uf.A[u * NY + y] += a; M.uf.E[u * NY + y] += e;   // linhas de UF: todas as UFs do bioma
    if (!inU) continue;
    M.biome.A[b * NY + y] += a; M.biome.E[b * NY + y] += e;
    const k = CLASS_COVER[F.c[i]]; M.cover.A[k * NY + y] += a; M.cover.E[k * NY + y] += e;
  }
  return M;
}
function rampColors() { return css('--ramp').split(',').map(x => x.trim()); }
function hexRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function rampAt(stops, t) {
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(x)), f = x - i;
  const a = hexRgb(stops[i]), b = hexRgb(stops[i + 1]);
  return { color: 'rgb(' + a.map((v, j) => Math.round(v + (b[j] - v) * f)).join(',') + ')', step: x };
}
function cellText(v) {
  if (v === null || !(v > 0)) return '-';
  const ms = S.measure;
  if (ms === 'emiss') { const x = v / 1e6; return x < 0.01 ? '<0,01' : nf(x >= 100 ? 0 : x >= 10 ? 1 : 2).format(x); }
  if (ms === 'area') { const x = v / 1e3; return x < 0.1 ? '<0,1' : nf(x >= 100 ? 0 : 1).format(x); }
  return v < 0.01 ? '<0,01' : nf(v >= 100 ? 0 : v >= 10 ? 1 : 2).format(v);
}
function matrixUnit() {
  const ms = S.measure, g = GAS[S.gas];
  return ms === 'emiss' ? 'Mt ' + g.unit.slice(2) : ms === 'area' ? 'mil ha' : g.unit + '/km²';
}
// rows: [{label, A[], E[], T, selected}] ; totT = território do total
function renderMatrix(id, head, rows, totT) {
  const tbl = $(id); tbl.textContent = '';
  const stops = rampColors(), flip = +css('--ramp-ink-flip');
  const vals = rows.map(r => YEARS.map((_, y) => measureOf(r.A[y], r.E[y], r.T)));
  const max = Math.max(0, ...vals.flat().filter(v => v !== null));
  const thead = tbl.createTHead().insertRow();
  [head, ...YEARS.map(y => y === LAST.slice(0, 4) && LAST_YEAR_PARTIAL ? y + '*' : y), 'Total'].forEach(h => {
    const th = document.createElement('th'); th.scope = 'col'; th.textContent = h; thead.appendChild(th); });
  const tb = tbl.createTBody();
  rows.forEach((r, ri) => {
    const tr = tb.insertRow(); if (r.selected) tr.className = 'sel';
    const th = document.createElement('th'); th.scope = 'row'; th.textContent = r.label; if (r.title) th.title = r.title; tr.appendChild(th);
    vals[ri].forEach(v => {
      const td = tr.insertCell(); td.textContent = cellText(v);
      if (v > 0 && max > 0) {
        const c = rampAt(stops, v / max); td.style.background = c.color; td.className = 'v';
        if (c.step >= flip) td.style.color = '#fbf8f2';
      }
    });
    let A = 0, E = 0; YEARS.forEach((_, y) => { A += r.A[y]; E += r.E[y]; });
    const td = tr.insertCell(); td.className = 'tot'; td.textContent = cellText(measureOf(A, E, r.T));
  });
  const tf = tbl.createTFoot().insertRow();
  const th = document.createElement('th'); th.scope = 'row'; th.textContent = 'Total'; tf.appendChild(th);
  let GA = 0, GE = 0;
  YEARS.forEach((_, y) => {
    let A = 0, E = 0; rows.forEach(r => { A += r.A[y]; E += r.E[y]; }); GA += A; GE += E;
    tf.insertCell().textContent = cellText(measureOf(A, E, totT));
  });
  tf.insertCell().textContent = cellText(measureOf(GA, GE, totT));
}
function renderMatrices() {
  const M = aggregateYears();
  const bSel = S.biome === 'all' ? -1 : +S.biome, uSel = S.uf === 'all' ? -1 : +S.uf;
  const slice = (arr, i) => ({ A: arr.A.subarray(i * NY, (i + 1) * NY), E: arr.E.subarray(i * NY, (i + 1) * NY) });
  const has = v => Array.from(v.A).some(x => x > 0);
  const what = measureName() + ' (' + matrixUnit() + ')';
  const shade = ' · sombreamento proporcional ao valor da célula';
  const bName = bSel < 0 ? 'todos os biomas' : BIOMES[bSel];
  const uName = uSel < 0 ? 'todas as UFs' : DATA.ufs[uSel].sigla;

  const ufRows = DATA.ufs.map((u, i) => ({ label: u.sigla, title: u.nome, ...slice(M.uf, i),
    T: territory(bSel, i), selected: i === uSel })).filter(has);
  renderMatrix('mxUF', 'UF', ufRows, territory(bSel, -1));
  $('tMxUF').textContent = 'UF × ano';
  $('sMxUF').textContent = what + ' · ' + bName + shade;

  const bRows = BIOMES.map((b, i) => ({ label: b, ...slice(M.biome, i), T: territory(i, uSel), selected: i === bSel })).filter(has);
  renderMatrix('mxBiome', 'Bioma', bRows, territory(bSel, uSel));
  $('sMxBiome').textContent = what + ' · ' + uName + shade;

  const T = territory(bSel, uSel);
  const cRows = COVER.map(([name], k) => ({ label: name, ...slice(M.cover, k), T })).filter(has);
  renderMatrix('mxCover', 'Cobertura', cRows, T);
  $('sMxCover').textContent = what + ' · ' + bName + ' · ' + uName + shade;
  $('mxNote').textContent = (LAST_YEAR_PARTIAL ? '*' + LAST.slice(0, 4) + ' até ' + MON[+LAST.slice(5) - 1] + '. ' : '')
    + (S.measure === 'dens' ? 'Densidade: emissão ÷ área do território da linha (cobertura: do recorte inteiro). ' : '')
    + 'As matrizes ignoram o filtro de período.';
}

// ---------- tabela ----------
const HEAD = ['Mês', 'Área queimada (ha)', 'CO₂ (t)', 'CH₄ (t CO₂e)', 'N₂O (t CO₂e)', 'CO₂e total (t)', 'Densidade CO₂e (t/km²)'];
let tableRows = [];
function renderTable(R) {
  tableRows = [];
  for (let m = R.m1; m >= R.m0; m--) {
    const a = monthSum(R, m)[0], c2 = R.mG[m * 3], c4 = R.mG[m * 3 + 1], n2 = R.mG[m * 3 + 2], tot = c2 + c4 + n2;
    tableRows.push([MONTHS[m], a, c2, c4, n2, tot, R.T > 0 ? tot / R.T : null]);
  }
  const thead = $('tbl').tHead; thead.textContent = '';
  const trh = thead.insertRow();
  HEAD.forEach(h => { const th = document.createElement('th'); th.textContent = h; th.scope = 'col'; trh.appendChild(th); });
  const tb = $('tbl').tBodies[0]; tb.textContent = '';
  tableRows.forEach(r => {
    const tr = tb.insertRow();
    r.forEach((v, j) => { tr.insertCell().textContent = j === 0 ? mLong(v) : v === null ? '—' : nf(j === 6 ? 3 : 0).format(v); });
  });
}
$('dlSlice').addEventListener('click', () => {
  const esc = s => /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  const lines = [HEAD.map(esc).join(',')].concat(tableRows.map(r =>
    r.map((v, j) => j === 0 ? v : v === null ? '' : v.toFixed(j === 6 ? 5 : 1)).join(',')));
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'monitor_emissoes_' + sliceText().normalize('NFD').replace(/[^\w]+/g, '_') + '.csv';
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});

// ---------- barra de filtros fixa ----------
const filtersEl = $('filters'), layoutEl = $('layout');
const sideMQ = matchMedia('(min-width: 1100px)');
function paintToggle() {
  const c = filtersEl.classList.contains('collapsed'), side = sideMQ.matches;
  $('fChev').textContent = side ? (c ? '▸' : '◂') : (c ? '▾' : '▴');
  $('fToggleText').textContent = c ? (side ? 'Filtros' : 'Mostrar filtros') : 'Minimizar filtros';
}
function setCollapsed(c) {
  filtersEl.classList.toggle('collapsed', c);
  layoutEl.classList.toggle('side-collapsed', c);
  $('fToggle').setAttribute('aria-expanded', String(!c));
  paintToggle();
  try { localStorage.setItem('monitorFiltersCollapsed', c ? '1' : '0'); } catch (e) { /* sem armazenamento */ }
}
$('fToggle').addEventListener('click', () => setCollapsed(!filtersEl.classList.contains('collapsed')));
if (sideMQ.addEventListener) sideMQ.addEventListener('change', paintToggle);
try { if (localStorage.getItem('monitorFiltersCollapsed') === '1') setCollapsed(true); } catch (e) { /* ok */ }
if ('IntersectionObserver' in window) {
  const sentinel = document.createElement('div'); sentinel.style.height = '1px';
  layoutEl.parentNode.insertBefore(sentinel, layoutEl);
  new IntersectionObserver(([en]) => filtersEl.classList.toggle('stuck', !en.isIntersecting)).observe(sentinel);
}
function renderSlice() {
  const el = $('slice'); el.textContent = '';
  const b = document.createElement('b'); b.textContent = measureName();
  el.append(b, document.createTextNode(' · ' + sliceText()));
}

// ---------- página de método ----------
const MT = DATA.method;
const CATS = Object.keys(MT.ef.CO2);
const fmtN = (v, d) => new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function tableFrom(id, head, rows) {
  const t = $(id); t.textContent = '';
  const tr = t.createTHead().insertRow(); head.forEach(h => { const th = el('th', '', h); th.scope = 'col'; tr.appendChild(th); });
  const tb = t.createTBody();
  rows.forEach(r => { const row = tb.insertRow(); r.forEach((c, j) => {
    if (j === 0) { const th = el('th', '', c); th.scope = 'row'; row.appendChild(th); }
    else { const td = row.insertCell(); if (c && typeof c === 'object') { td.textContent = c.t; if (c.bg) td.style.background = c.bg; if (c.fg) td.style.color = c.fg; } else td.textContent = c; } }); });
}
function poolText(coef) {
  return [['AGB', 'biomassa aérea'], ['DW', 'madeira morta'], ['LI', 'serrapilheira']].filter(([k]) => coef[k])
    .map(([k, n]) => (coef[k] !== 1 ? fmtN(coef[k], 2) + '×' : '') + n).join(' + ');
}
function buildMethod() {
  const box = $('mClasses'); box.textContent = '';
  CATS.forEach(cat => {
    const c = el('div', 'mcard');
    c.append(el('div', 'k', MT.antropic.includes(cat) ? 'agropecuária' : 'nativa'), el('h4', '', cat));
    const l = el('div', 'clist');
    MT.classes[cat].forEach(x => { const s = el('span'); const i = el('i'); i.style.background = x.color; s.append(i, document.createTextNode(x.name + ' (' + x.id + ')')); l.appendChild(s); });
    c.appendChild(l); box.appendChild(c);
  });
  const anyB = Object.keys(MT.bioma)[0];
  tableFrom('mPools', ['Categoria', 'Compartimentos'], CATS.map(cat => [cat,
    MT.antropic.includes(cat) ? 'estoque médio do bioma' : poolText(MT.bioma[anyB][cat].coef).replace(/^0,26×/, '26% da ')]));
  const stops = rampColors(), biomes = Object.keys(MT.bioma);
  const cfs = biomes.flatMap(b => CATS.map(c => MT.bioma[b][c].cf)), lo = Math.min(...cfs), hi = Math.max(...cfs);
  tableFrom('mCf', ['Categoria', ...biomes], CATS.map(cat => [cat, ...biomes.map(b => {
    const v = MT.bioma[b][cat].cf, t = (v - lo) / (hi - lo || 1), c = rampAt(stops, 0.1 + 0.7 * t);
    return { t: fmtN(v, 2), bg: c.color, fg: c.step >= +css('--ramp-ink-flip') ? '#fbf8f2' : '' }; })]));
  tableFrom('mEf', ['Categoria', 'CO₂', 'CH₄', 'N₂O', 'CO₂e por kg MS (g)'], CATS.map(cat => [cat,
    fmtN(MT.ef.CO2[cat], 0), fmtN(MT.ef.CH4[cat], 1), fmtN(MT.ef.N2O[cat], 2),
    fmtN(MT.ef.CO2[cat] + MT.ef.CH4[cat] * MT.gwp.CH4 + MT.ef.N2O[cat] * MT.gwp.N2O, 0)]));
  $('mLastCov').textContent = 'Para meses posteriores a ' + MT.last_cov_year + ', utiliza-se a cobertura de ' + MT.last_cov_year + ', a mais recente disponível.';
  buildCalc();
}
const C = { bioma: 'Cerrado', cat: 'Formação Savânica', AGB: 30, DW: 5, LI: 4 };
function buildCalc() {
  const biomes = Object.keys(MT.bioma);
  const segC = (id, key, items) => {
    const box = $(id); box.textContent = '';
    items.forEach(v => { const b = el('button', '', v); b.type = 'button'; b.setAttribute('aria-pressed', String(C[key] === v));
      b.addEventListener('click', () => { C[key] = v; buildCalc(); }); box.appendChild(b); });
  };
  segC('cBioma', 'bioma', biomes); segC('cCat', 'cat', CATS);
  const f = MT.bioma[C.bioma][C.cat], antr = MT.antropic.includes(C.cat);
  const pools = $('cPools'); pools.textContent = '';
  if (antr) pools.appendChild(el('p', 'note', 'Carbono médio de ' + C.cat.toLowerCase() + ' no ' + C.bioma + ': ' + fmtN(f.c_mean, 2) + ' t C/ha (usado como AGB).'));
  else [['AGB', 'Biomassa aérea', 250], ['DW', 'Madeira morta', 40], ['LI', 'Serrapilheira', 20]].forEach(([k, n, max]) => {
    const used = f.coef[k] > 0;
    const lab = el('label', 'sl'); const nm = el('span', '', n + (used ? '' : ' (não usada)'));
    const inp = document.createElement('input'); inp.type = 'range'; inp.min = 0; inp.max = max; inp.step = 0.5; inp.value = C[k]; inp.disabled = !used;
    const sv = el('span', 'sv', fmtN(C[k], 1));
    inp.addEventListener('input', () => { C[k] = +inp.value; sv.textContent = fmtN(C[k], 1); renderCalc(); });
    lab.append(nm, inp, sv); pools.appendChild(lab);
  });
  renderCalc();
}
function renderCalc() {
  const f = MT.bioma[C.bioma][C.cat], antr = MT.antropic.includes(C.cat);
  const stock = antr ? f.c_mean : f.coef.AGB * C.AGB + f.coef.DW * C.DW + f.coef.LI * C.LI;
  const burned = stock * f.cf, dm = burned / MT.carbon_fraction;
  const gas = { CO2: dm * MT.ef.CO2[C.cat] / 1000, CH4: dm * MT.ef.CH4[C.cat] / 1000 * MT.gwp.CH4, N2O: dm * MT.ef.N2O[C.cat] / 1000 * MT.gwp.N2O };
  const tot = gas.CO2 + gas.CH4 + gas.N2O;
  const ch = $('cChain'); ch.textContent = '';
  const term = (v, u, cls) => { const t = el('div', 'term' + (cls ? ' ' + cls : '')); t.append(el('div', 'v', v), el('div', 'u', u)); return t; };
  ch.append(term(fmtN(stock, 1), antr ? 't C/ha (média do bioma)' : 't C/ha disponível'), el('div', 'op', '×'),
    term(fmtN(f.cf, 3), 'fator de combustão'), el('div', 'op', '='), term(fmtN(burned, 1), 't C/ha queimado'), el('div', 'op', '÷'),
    term('0,47', 'fração de C', 'hl'), el('div', 'op', '='), term(fmtN(dm, 1), 't MS/ha'), el('div', 'op', '→'),
    term(fmtN(tot, 1), 't CO₂e/ha', 'out'));
  const gb = $('cGas'); gb.textContent = '';
  [['CO₂', gas.CO2], ['CH₄', gas.CH4], ['N₂O', gas.N2O]].forEach(([n, v]) => {
    const r = el('div', 'gbar'); const t = el('div', 't'); const sp = el('span'); sp.style.width = (tot > 0 ? v / tot * 100 : 0) + '%'; t.appendChild(sp);
    r.append(el('span', '', n), t, el('span', 'f', fmtN(v, 2) + (n === 'CO₂' ? ' t CO₂' : ' t CO₂e'))); gb.appendChild(r);
  });
  $('cNote').textContent = 'Fatores de emissão de ' + C.cat.toLowerCase() + ': CO₂ ' + fmtN(MT.ef.CO2[C.cat], 0) + ', CH₄ ' + fmtN(MT.ef.CH4[C.cat], 1)
    + ', N₂O ' + fmtN(MT.ef.N2O[C.cat], 2) + ' g por kg de matéria seca.';
}

// ---------- abas ----------
function route() {
  const met = location.hash.startsWith('#m') && location.hash !== '#painel';
  $('pagePainel').hidden = met; $('pageMetodo').hidden = !met;
  $('tabPainel').setAttribute('aria-current', met ? 'false' : 'page');
  $('tabMetodo').setAttribute('aria-current', met ? 'page' : 'false');
  if (met && location.hash === '#metodo') window.scrollTo(0, 0);
}
window.addEventListener('hashchange', route);

// ---------- orquestração ----------
function renderAll() {
  const R = aggregate();
  renderSlice();
  renderKPIs(R); renderMonthly(R); renderSide(R); renderAnnual(R); renderClass(R); renderUF(R); renderMatrices(); renderTable(R);
}

$('meta').textContent = 'Dados de ' + mLong(MONTHS[0]) + ' a ' + mLong(LAST) + ' · ' + NM + ' meses · '
  + DATA.ufs.length + ' UFs · MapBiomas Fogo / IPAM';
$('foot').textContent = 'MapBiomas Fogo / IPAM · base completa em __CSV_NAME__ · página gerada em __BUILD_DATE__.';
renderAll();
buildMethod();
route();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULTS["data"], help="pasta com os CSVs mensais")
    ap.add_argument("--csv", type=Path, default=DEFAULTS["csv"],
                    help="CSV consolidado (gravado a partir dos mensais; lido se não houver mensais)")
    ap.add_argument("--html", type=Path, default=DEFAULTS["html"])
    ap.add_argument("--chart-js", type=Path, default=DEFAULTS["chart_js"])
    ap.add_argument("--csv-href", default=DEFAULTS["csv_href"], help="link do CSV completo no HTML")
    ap.add_argument("--territory", type=Path, default=DEFAULTS["territory"],
                    help="área do território por Bioma × UF (area_territorio_bioma_uf.py)")
    args = ap.parse_args()

    df, from_monthly = load_all(args.data, args.csv)
    if from_monthly:
        df.drop(columns=["ym"]).to_csv(args.csv, index=False, encoding="utf-8")
    payload = build_payload(df, pd.read_csv(args.territory))
    html = (HTML_TEMPLATE
            .replace("__CHART_JS__", args.chart_js.read_text(encoding="utf-8"))
            .replace("__CSV_HREF__", args.csv_href)
            .replace("__CSV_NAME__", Path(args.csv_href).name)
            .replace("__BUILD_DATE__", pd.Timestamp.now().strftime("%d/%m/%Y"))
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))
    args.html.write_text(html, encoding="utf-8")

    print(f"CSV consolidado: {args.csv} ({len(df)} linhas)")
    print(f"Dashboard HTML:  {args.html} ({len(html) // 1024} KB)")
    print(f"Período: {payload['months'][0]} .. {payload['months'][-1]} ({len(payload['months'])} meses)")


if __name__ == "__main__":
    main()
