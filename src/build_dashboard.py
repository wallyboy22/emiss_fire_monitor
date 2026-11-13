"""Une os CSVs mensais do monitor e gera um dashboard HTML (Chart.js) para análise.

Métricas disponíveis no eixo Y:
  - Área queimada (km²)
  - Emissão de CO2 (t)
  - Intensidade de emissão (t CO2/ha) = emissão ÷ área (média ponderada)

Dimensões de detalhamento:
  - Por bioma (série temporal, dispersão, total)
  - Por classe de cobertura (série temporal e total, pelo nível selecionado)
"""
import json
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "monthly"
OUT_CSV = BASE / "data" / "consolidado_monitor_emissoes_bioma_uf.csv"
OUT_HTML = BASE / "index.html"
CHART_JS = BASE / "assets" / "chart.umd.min.js"

BIOMES = ["Amazônia", "Caatinga", "Cerrado", "Mata Atlântica", "Pampa", "Pantanal"]
NIVEIS = ["Nível 0", "Nível 1", "Nível 1_1", "Nível 2", "Nível 3", "Nível 4"]

AREA_COL = "Área km²"
EMISS_COL = "Emissão CO2"


def load_all():
    frames = [pd.read_csv(fp) for fp in sorted(DATA.glob("*.csv"))]
    df = pd.concat(frames, ignore_index=True) if frames else pd.read_csv(OUT_CSV)
    df["ym"] = df["Ano"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2)
    return df


def _pivot(df, months, group_col, value_col):
    return (
        df.pivot_table(index="ym", columns=group_col, values=value_col, aggfunc="sum", fill_value=0.0)
        .reindex(months, fill_value=0.0)
    )


def build_payload(df):
    months = sorted(df["ym"].unique())

    # ---- por bioma ----
    area_pivot = _pivot(df, months, "Bioma", AREA_COL)
    emiss_pivot = _pivot(df, months, "Bioma", EMISS_COL)
    area_by_biome = {b: [round(float(area_pivot.loc[m, b]), 3) for m in months] for b in BIOMES}
    emissao_by_biome = {b: [round(float(emiss_pivot.loc[m, b]), 3) for m in months] for b in BIOMES}

    biome_area = df.groupby("Bioma")[AREA_COL].sum()
    biome_emiss = df.groupby("Bioma")[EMISS_COL].sum()

    # Novos CSVs incluem a interseção espacial Bioma × UF. Os CSVs históricos
    # continuam carregáveis; nesse caso o painel por UF informa ausência de dados.
    ufs = sorted(df["SIGLA_UF"].dropna().astype(str).unique()) if "SIGLA_UF" in df else []
    uf_monthly = {}
    biome_uf_totals = {}
    if ufs:
        for sigla in ufs:
            sub = df[df["SIGLA_UF"].astype(str) == sigla]
            ap = _pivot(sub, months, "SIGLA_UF", AREA_COL)
            ep = _pivot(sub, months, "SIGLA_UF", EMISS_COL)
            uf_monthly[sigla] = {
                "area": [round(float(ap.loc[m, sigla]), 3) for m in months],
                "emissao": [round(float(ep.loc[m, sigla]), 3) for m in months],
            }
        grouped = df.groupby(["Bioma", "SIGLA_UF"]).agg(area=(AREA_COL, "sum"), emissao=(EMISS_COL, "sum"))
        biome_uf_totals = {
            b: {uf: {"area": round(float(grouped.loc[(b, uf), "area"]), 3),
                     "emissao": round(float(grouped.loc[(b, uf), "emissao"]), 3)}
                for uf in ufs if (b, uf) in grouped.index}
            for b in BIOMES
        }

    # ---- por classe (um nível por vez) ----
    class_series = {}
    class_totals = {}
    for lv in NIVEIS:
        ap = _pivot(df, months, lv, AREA_COL)
        ep = _pivot(df, months, lv, EMISS_COL)
        ordered = list(df.groupby(lv)[AREA_COL].sum().sort_values(ascending=False).index)
        class_series[lv] = {
            "classes": ordered,
            "area": {c: [round(float(ap.loc[m, c]), 3) for m in months] for c in ordered},
            "emissao": {c: [round(float(ep.loc[m, c]), 3) for m in months] for c in ordered},
        }
        g = df.groupby(lv).agg(area=(AREA_COL, "sum"), emissao=(EMISS_COL, "sum")).reindex(ordered)
        class_totals[lv] = {
            "labels": ordered,
            "area": [round(float(v), 3) for v in g["area"]],
            "emissao": [round(float(v), 3) for v in g["emissao"]],
        }

    return {
        "months": months,
        "biomes": BIOMES,
        "niveis": NIVEIS,
        "area_by_biome": area_by_biome,
        "emissao_by_biome": emissao_by_biome,
        "biome_area_total": {b: round(float(biome_area.get(b, 0.0)), 3) for b in BIOMES},
        "biome_emissao_total": {b: round(float(biome_emiss.get(b, 0.0)), 3) for b in BIOMES},
        "ufs": ufs,
        "uf_monthly": uf_monthly,
        "biome_uf_totals": biome_uf_totals,
        "class_series": class_series,
        "class_totals": class_totals,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de Emissões — Fogo por Bioma, UF e Classe · MapBiomas Fogo / IPAM</title>
<script>
__CHART_JS__
</script>
<style>
  :root{--bg:#f4f5f7;--card:#fff;--ink:#1c2733;--muted:#64748b;--accent:#e65100;--accent2:#ff9800;--line:#e5e9ef}
  *{box-sizing:border-box}
  body{margin:0;font-family:'Segoe UI',system-ui,-apple-system,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
  header{background:linear-gradient(135deg,#1c2733,#33414f);color:#fff;padding:26px 32px}
  header h1{margin:0 0 6px;font-size:22px;letter-spacing:.2px}
  header p{margin:0;color:#c7d0da;font-size:13.5px}
  header .accent{color:var(--accent2);font-weight:600}
  .wrap{max-width:1280px;margin:0 auto;padding:24px 20px 60px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px;margin-bottom:20px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
  .kpi .label{font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px}
  .kpi .value{font-size:24px;font-weight:700;line-height:1.1}
  .kpi .sub{font-size:12px;color:var(--muted);margin-top:6px}
  .kpi.accent{border-left:4px solid var(--accent)}
  .controls{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin-bottom:20px}
  .control{display:flex;flex-direction:column;gap:6px}
  .control label{font-size:12px;color:var(--muted);font-weight:600;letter-spacing:.3px}
  select{min-width:210px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:14px;color:var(--ink);cursor:pointer}
  select:focus{outline:2px solid var(--accent2)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:20px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
  .card h2{margin:0 0 4px;font-size:15.5px}
  .card .hint{margin:0 0 14px;font-size:12.5px;color:var(--muted)}
  .chart-box{position:relative;height:360px}
  .chart-box.tall{height:440px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
  @media(max-width:840px){.grid2{grid-template-columns:1fr}}
  footer{color:var(--muted);font-size:12px;text-align:center;margin-top:8px}
  footer code{background:#eef1f5;padding:1px 5px;border-radius:4px}
</style>
</head>
<body>
<header>
  <h1>Monitor de Emissões — Fogo por Bioma, UF e Classe <span class="accent">(IBGE)</span></h1>
  <p>MapBiomas Fogo / IPAM · uso e cobertura MapBiomas Coleção 11 · emissões mensais · 2019–2026</p>
</header>

<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <div class="controls">
    <div class="control">
      <label for="metricSel">Métrica (eixo Y)</label>
      <select id="metricSel">
        <option value="area">Área queimada (km²)</option>
        <option value="emissao">Emissão de CO2 (t)</option>
        <option value="intensidade">Intensidade — Emissão ÷ Área (t CO2/ha)</option>
      </select>
    </div>
    <div class="control">
      <label for="periodSel">Periodicidade</label>
      <select id="periodSel">
        <option value="mensal">Mensal</option>
        <option value="anual">Anual</option>
      </select>
    </div>
    <div class="control">
      <label for="nivelSel">Nível de classe</label>
      <select id="nivelSel"></select>
    </div>
    <div class="control">
      <label for="biomeSel">Bioma</label>
      <select id="biomeSel">
        <option value="Todos">Todos os biomas</option>
      </select>
    </div>
  </div>

  <div class="card">
    <h2>Série temporal — por bioma</h2>
    <p class="hint">Empilhado por bioma (segue o filtro de bioma e a periodicidade). Clique num bioma na legenda para esconder/mostrar.</p>
    <div class="chart-box tall"><canvas id="chartBiomaSerie"></canvas></div>
  </div>

  <div class="card">
    <h2>Série temporal — por classe de cobertura</h2>
    <p class="hint">Empilhado por classe no nível selecionado (todos os biomas somados, segue a periodicidade).</p>
    <div class="chart-box tall"><canvas id="chartClasseSerie"></canvas></div>
  </div>

  <div class="card">
    <h2>Emissão × Área (dispersão)</h2>
    <p class="hint">Cada ponto é um bioma × período (mês ou ano). A reta tracejada é a <b>média ponderada</b>: emissão total ÷ área total (t CO2/ha).</p>
    <div class="chart-box tall"><canvas id="chartScatter"></canvas></div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>Total por bioma</h2>
      <p class="hint">Acumulado no período (métrica selecionada).</p>
      <div class="chart-box"><canvas id="chartBioma"></canvas></div>
    </div>
    <div class="card">
      <h2>Total por classe</h2>
      <p class="hint" id="classeHint">Acumulado no período, pelo nível selecionado.</p>
      <div class="chart-box"><canvas id="chartClasse"></canvas></div>
    </div>
  </div>

  <div class="card">
    <h2>Total por UF — no bioma selecionado</h2>
    <p class="hint" id="ufHint">Os dados serão exibidos quando os CSVs com a dimensão SIGLA_UF estiverem carregados.</p>
    <div class="chart-box"><canvas id="chartUF"></canvas></div>
  </div>

  <footer>
    Fonte: <code>csv-monitor-mensal-emissoes-bioma-uf_col11_2026_*.csv</code> · consolidado em <code>consolidado_monitor_emissoes_bioma_uf.csv</code>.
  </footer>
</div>

<script>
const DATA = __DATA__;

const BIOME_COLORS = {
  'Amazônia': '#2e7d32', 'Caatinga': '#c49000', 'Cerrado': '#e65100',
  'Mata Atlântica': '#1565c0', 'Pampa': '#43a047', 'Pantanal': '#6a1b9a',
};

const MONTH_SHORT = m => {
  const [y, mo] = m.split('-');
  const n = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
  return n[+mo - 1] + '/' + y.slice(2);
};
const MONTH_LABELS = DATA.months.map(MONTH_SHORT);
const YEARS = [...new Set(DATA.months.map(m => m.split('-')[0]))];
const YEAR_MONTHS = {};
DATA.months.forEach((m, i) => { const y = m.split('-')[0]; (YEAR_MONTHS[y] = YEAR_MONTHS[y] || []).push(i); });

const METRICS = {
  area: { label: 'Área queimada', unit: 'km²' },
  emissao: { label: 'Emissão de CO2', unit: 't CO2' },
  intensidade: { label: 'Intensidade', unit: 't CO2/ha' },
};

function fmt(n, d = 0) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return n.toLocaleString('pt-BR', { maximumFractionDigits: d });
}

// cor estável por rótulo de classe (mesma classe = mesma cor em qualquer nível)
function colorFor(label) {
  let h = 0;
  for (let i = 0; i < label.length; i++) h = (h * 31 + label.charCodeAt(i)) % 360;
  return 'hsl(' + h + ', 58%, 45%)';
}

// ---- séries por métrica e periodicidade ----
function periodLabels(period) {
  return period === 'anual' ? YEARS : MONTH_LABELS;
}
function periodSeries(metric, areaArr, emissArr, period) {
  const r3 = n => Math.round(n * 1000) / 1000;
  if (period === 'anual') {
    return YEARS.map(y => {
      const idx = YEAR_MONTHS[y];
      let a = 0, e = 0;
      idx.forEach(i => { a += areaArr[i]; e += emissArr[i]; });
      if (metric === 'area') return r3(a);
      if (metric === 'emissao') return r3(e);
      const ha = a * 100;
      return ha > 0 ? +(e / ha).toFixed(3) : null;
    });
  }
  if (metric === 'area') return areaArr;
  if (metric === 'emissao') return emissArr;
  return emissArr.map((e, i) => { const ha = areaArr[i] * 100; return ha > 0 ? +(e / ha).toFixed(3) : null; });
}
function serieBioma(metric, b, period) {
  return periodSeries(metric, DATA.area_by_biome[b], DATA.emissao_by_biome[b], period);
}
function serieClasse(metric, lv, c, period) {
  const S = DATA.class_series[lv];
  return periodSeries(metric, S.area[c], S.emissao[c], period);
}

// ---- totais por métrica ----
function biomeTotal(metric, b) {
  if (metric === 'area') return DATA.biome_area_total[b];
  if (metric === 'emissao') return DATA.biome_emissao_total[b];
  const ha = DATA.biome_area_total[b] * 100;
  return ha > 0 ? +(DATA.biome_emissao_total[b] / ha).toFixed(3) : null;
}
function classVal(metric, lv, i) {
  const t = DATA.class_totals[lv];
  if (metric === 'area') return t.area[i];
  if (metric === 'emissao') return t.emissao[i];
  const ha = t.area[i] * 100;
  return ha > 0 ? +(t.emissao[i] / ha).toFixed(3) : null;
}

// ---- referências dos selects ----
const metricSel = document.getElementById('metricSel');
const nivelSel = document.getElementById('nivelSel');
const biomeSel = document.getElementById('biomeSel');
const periodSel = document.getElementById('periodSel');

DATA.niveis.forEach(n => {
  const o = document.createElement('option');
  o.value = n; o.textContent = n;
  nivelSel.appendChild(o);
});
DATA.biomes.forEach(b => {
  const o = document.createElement('option');
  o.value = b; o.textContent = b;
  biomeSel.appendChild(o);
});

// ---- options comuns ----
function baseOptions(stacked, unit, indexAxis) {
  const isH = indexAxis === 'y';
  const valueAxis = isH ? 'x' : 'y';
  const catAxis = isH ? 'y' : 'x';
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    indexAxis: indexAxis,
    plugins: {
      legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8, padding: 12 } },
      tooltip: { callbacks: { label: ctx => ' ' + ctx.dataset.label + ': ' + fmt(ctx.parsed[valueAxis]) + ' ' + unit } },
    },
    scales: {
      [valueAxis]: { stacked, beginAtZero: true, title: { display: true, text: unit }, ticks: { callback: v => fmt(v) } },
      [catAxis]: { stacked, grid: { display: false }, ticks: isH ? {} : { maxRotation: 0, autoSkip: true, maxTicksLimit: 16 } },
    },
  };
}

function applyMetric(chart, metric, indexAxis) {
  const unit = METRICS[metric].unit;
  const valueAxis = indexAxis === 'y' ? 'x' : 'y';
  chart.options.scales[valueAxis].title.text = unit;
  chart.options.plugins.tooltip.callbacks.label =
    ctx => ' ' + ctx.dataset.label + ': ' + fmt(ctx.parsed[valueAxis]) + ' ' + unit;
}

// ---- instâncias ----
const biomaSerieChart = new Chart(document.getElementById('chartBiomaSerie'), {
  type: 'bar', data: { labels: MONTH_LABELS, datasets: [] }, options: baseOptions(true, 'km²', 'x'),
});
const classeSerieChart = new Chart(document.getElementById('chartClasseSerie'), {
  type: 'bar', data: { labels: MONTH_LABELS, datasets: [] }, options: baseOptions(true, 'km²', 'x'),
});
const scatterChart = new Chart(document.getElementById('chartScatter'), {
  type: 'scatter',
  data: { datasets: [] },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'nearest', intersect: false },
    plugins: {
      legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8, padding: 12 } },
      tooltip: { callbacks: { label: ctx => ' ' + ctx.dataset.label + ': ' + fmt(ctx.parsed.y) + ' t em ' + fmt(ctx.parsed.x) + ' ha' } },
    },
    scales: {
      x: { title: { display: true, text: 'Área queimada (ha)' }, ticks: { callback: v => fmt(v) } },
      y: { title: { display: true, text: 'Emissão (t CO2)' }, beginAtZero: true, ticks: { callback: v => fmt(v) } },
    },
  },
});
const biomaChart = new Chart(document.getElementById('chartBioma'), {
  type: 'bar', data: { labels: DATA.biomes, datasets: [] }, options: baseOptions(false, 'km²', 'y'),
});
const classeChart = new Chart(document.getElementById('chartClasse'), {
  type: 'bar', data: { labels: [], datasets: [] }, options: baseOptions(false, 'km²', 'y'),
});
const ufChart = new Chart(document.getElementById('chartUF'), {
  type: 'bar', data: { labels: [], datasets: [] }, options: baseOptions(false, 'km²', 'y'),
});

// ---- render ----
function selectedBiomes() {
  return biomeSel.value === 'Todos' ? DATA.biomes : [biomeSel.value];
}

function renderKPI() {
  const biomes = selectedBiomes();
  let area = 0, emiss = 0;
  biomes.forEach(b => { area += DATA.biome_area_total[b]; emiss += DATA.biome_emissao_total[b]; });
  const ha = area * 100;
  const intensidade = ha > 0 ? emiss / ha : 0;

  // pico (mês ou ano) de área
  let pk = 0, pkIdx = 0, pkLabels;
  if (periodSel.value === 'anual') {
    pkLabels = YEARS;
    YEARS.forEach((y, yi) => {
      let a = 0;
      YEAR_MONTHS[y].forEach(i => biomes.forEach(b => a += DATA.area_by_biome[b][i]));
      if (a > pk) { pk = a; pkIdx = yi; }
    });
  } else {
    pkLabels = MONTH_LABELS;
    const areaSerie = DATA.months.map((_, i) => biomes.reduce((s, b) => s + DATA.area_by_biome[b][i], 0));
    areaSerie.forEach((v, i) => { if (v > pk) { pk = v; pkIdx = i; } });
  }

  const topBiome = [...DATA.biomes].sort((a, b) => DATA.biome_area_total[b] - DATA.biome_area_total[a])[0];

  const cards = [
    { label: 'Área queimada', value: fmt(area) + ' km²', sub: '≈ ' + fmt(ha) + ' ha no período', accent: false },
    { label: 'Emissão de CO2', value: fmt(emiss / 1e6, 2) + ' Mt', sub: fmt(emiss) + ' t no período', accent: false },
    { label: 'Intensidade média', value: fmt(intensidade, 3) + ' t CO2/ha', sub: 'emissão ÷ área (média ponderada)', accent: true },
    { label: periodSel.value === 'anual' ? 'Pico anual de área' : 'Pico mensal de área', value: pkLabels[pkIdx], sub: fmt(pk) + ' km² · bioma líder: ' + topBiome, accent: false },
  ];
  document.getElementById('kpis').innerHTML = cards.map(c =>
    '<div class="kpi ' + (c.accent ? 'accent' : '') + '"><div class="label">' + c.label + '</div><div class="value">' + c.value + '</div><div class="sub">' + c.sub + '</div></div>'
  ).join('');
}

function renderBiomaSerie() {
  const metric = metricSel.value;
  const period = periodSel.value;
  const biomes = selectedBiomes();
  biomaSerieChart.data.labels = periodLabels(period);
  biomaSerieChart.data.datasets = biomes.map(b => ({
    label: b, data: serieBioma(metric, b, period), backgroundColor: BIOME_COLORS[b], borderRadius: 1,
  }));
  applyMetric(biomaSerieChart, metric, 'x');
  biomaSerieChart.update();
}

function renderClasseSerie() {
  const metric = metricSel.value;
  const period = periodSel.value;
  const S = DATA.class_series[nivelSel.value];
  classeSerieChart.data.labels = periodLabels(period);
  classeSerieChart.data.datasets = S.classes.map(c => ({
    label: c, data: serieClasse(metric, nivelSel.value, c, period), backgroundColor: colorFor(c), borderRadius: 1,
  }));
  applyMetric(classeSerieChart, metric, 'x');
  classeSerieChart.update();
}

function renderScatter() {
  const period = periodSel.value;
  const datasets = DATA.biomes.map(b => {
    const pts = [];
    if (period === 'anual') {
      YEARS.forEach(y => {
        const idx = YEAR_MONTHS[y];
        let a = 0, e = 0;
        idx.forEach(i => { a += DATA.area_by_biome[b][i] * 100; e += DATA.emissao_by_biome[b][i]; });
        if (a > 0) pts.push({ x: a, y: e });
      });
    } else {
      DATA.months.forEach((_, i) => {
        const ha = DATA.area_by_biome[b][i] * 100;
        const e = DATA.emissao_by_biome[b][i];
        if (ha > 0) pts.push({ x: ha, y: e });
      });
    }
    return { label: b, data: pts, backgroundColor: BIOME_COLORS[b], pointRadius: 3, pointHoverRadius: 5 };
  });

  let totE = 0, totHa = 0;
  DATA.biomes.forEach(b => { totE += DATA.biome_emissao_total[b]; totHa += DATA.biome_area_total[b] * 100; });
  const slope = totHa > 0 ? totE / totHa : 0;
  let maxHa = 0;
  datasets.forEach(ds => ds.data.forEach(p => { if (p.x > maxHa) maxHa = p.x; }));

  datasets.push({
    label: 'Média ponderada (' + fmt(slope, 3) + ' t/ha)',
    data: [{ x: 0, y: 0 }, { x: maxHa, y: slope * maxHa }],
    type: 'line', borderColor: '#111827', borderDash: [6, 4], borderWidth: 2,
    pointRadius: 0, fill: false, order: 0,
  });

  scatterChart.data.datasets = datasets;
  scatterChart.update();
}

function renderBioma() {
  const metric = metricSel.value;
  biomaChart.data.datasets = [{
    label: METRICS[metric].label,
    data: DATA.biomes.map(b => biomeTotal(metric, b)),
    backgroundColor: DATA.biomes.map(b => BIOME_COLORS[b]),
    borderRadius: 2,
  }];
  applyMetric(biomaChart, metric, 'y');
  biomaChart.update();
}

function renderClasse() {
  const metric = metricSel.value;
  const lv = nivelSel.value;
  const t = DATA.class_totals[lv];
  classeChart.data.labels = t.labels;
  classeChart.data.datasets = [{
    label: METRICS[metric].label,
    data: t.labels.map((_, i) => classVal(metric, lv, i)),
    backgroundColor: t.labels.map(colorFor),
    borderRadius: 2,
  }];
  applyMetric(classeChart, metric, 'y');
  classeChart.update();
}

function renderUF() {
  const metric = metricSel.value;
  const biome = biomeSel.value;
  const values = DATA.ufs.map(uf => {
    const t = DATA.biome_uf_totals[biome === 'Todos' ? DATA.biomes[0] : biome]?.[uf];
    if (!t || metric === 'area') return metric === 'area' && t ? t.area : 0;
    if (metric === 'emissao') return t.emissao;
    return t.area > 0 ? +(t.emissao / (t.area * 100)).toFixed(3) : null;
  });
  // Para "Todos", somar os seis biomas em cada UF.
  if (biome === 'Todos') DATA.ufs.forEach((uf, i) => {
    let area = 0, emissao = 0;
    DATA.biomes.forEach(b => { const t = DATA.biome_uf_totals[b]?.[uf]; if (t) { area += t.area; emissao += t.emissao; } });
    values[i] = metric === 'area' ? area : metric === 'emissao' ? emissao : area > 0 ? +(emissao / (area * 100)).toFixed(3) : null;
  });
  ufChart.data.labels = DATA.ufs;
  ufChart.data.datasets = [{ label: METRICS[metric].label, data: values, backgroundColor: '#1565c0', borderRadius: 2 }];
  applyMetric(ufChart, metric, 'y');
  ufChart.update();
  document.getElementById('ufHint').textContent = DATA.ufs.length
    ? 'Acumulado no período; filtro de bioma: ' + (biome === 'Todos' ? 'todos' : biome) + '.'
    : 'Os CSVs carregados ainda não têm SIGLA_UF. Gere/baixe os CSVs novos para habilitar este gráfico.';
}

function renderAll() {
  renderKPI();
  renderBiomaSerie();
  renderClasseSerie();
  renderScatter();
  renderBioma();
  renderClasse();
  renderUF();
}

metricSel.addEventListener('change', () => { renderBiomaSerie(); renderClasseSerie(); renderBioma(); renderClasse(); renderUF(); });
biomeSel.addEventListener('change', () => { renderKPI(); renderBiomaSerie(); renderUF(); });
nivelSel.addEventListener('change', () => { renderClasseSerie(); renderClasse(); });
periodSel.addEventListener('change', () => { renderKPI(); renderBiomaSerie(); renderClasseSerie(); renderScatter(); });

renderAll();
</script>
</body>
</html>
"""


def main():
    df = load_all()
    payload = build_payload(df)
    chart_js = CHART_JS.read_text(encoding="utf-8")
    html = HTML_TEMPLATE.replace("__CHART_JS__", chart_js).replace(
        "__DATA__", json.dumps(payload, ensure_ascii=False)
    )
    OUT_HTML.write_text(html, encoding="utf-8")

    print(f"CSV consolidado: {OUT_CSV} ({len(df)} linhas)")
    print(f"Dashboard HTML:  {OUT_HTML}")
    print(f"Período: {payload['months'][0]} .. {payload['months'][-1]} ({len(payload['months'])} meses)")


if __name__ == "__main__":
    main()
