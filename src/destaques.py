"""Página "Destaques do mês": relatório no formato dos destaques mensais do Monitor do Fogo,
com a emissão estimada ao lado da área queimada em cada bloco.

Gerada pelo build_dashboard.py a partir do mesmo payload do painel (tabela colunar de fatos),
mais os contornos de biomas e UFs (data/geo, gerados por geometrias.py) já projetados em SVG.
Todo o cálculo do mês escolhido acontece no navegador; ?m=AAAA-MM abre um mês específico.
"""
import json
import math
from pathlib import Path

BIOME_CD = {"Amazônia": 1, "Caatinga": 2, "Cerrado": 3, "Mata Atlântica": 4, "Pampa": 5, "Pantanal": 6}
# rótulos fora do mapa, com linha de chamada (territórios pequenos)
LEAD_UF = {"RN", "PB", "PE", "AL", "SE", "DF", "ES", "RJ"}
LEAD_BIOME = {"Mata Atlântica", "Pampa"}

# projeção equiretangular com escala de longitude no paralelo central
LON0, LAT0, LATC, K = -74.2, 5.6, -15.0, 15.0
COSC = math.cos(math.radians(LATC))
MAP_W, LEAD_W = 572, 92


def _proj(lon, lat):
    return (lon - LON0) * COSC * K, (LAT0 - lat) * K


def _dp(pts, tol):
    """Douglas-Peucker iterativo."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1e-9
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            x0, y0 = pts[i]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / n if n > 1e-9 else math.hypot(x0 - x1, y0 - y1)
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def _ring_area_centroid(r):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    a /= 2
    if abs(a) < 1e-9:
        return 0.0, r[0]
    return abs(a), (cx / (6 * a), cy / (6 * a))


def _polys(g):
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]


def _feature_svg(geom, tol=0.45):
    parts, best = [], (0.0, (0, 0))
    for poly in _polys(geom):
        for j, ring in enumerate(poly):
            pts = _dp([_proj(x, y) for x, y in ring], tol)
            if len(pts) < 4:
                continue
            area, c = _ring_area_centroid(pts[:-1])
            if area < 1.2:
                continue
            if j == 0 and area > best[0]:
                best = (area, c)
            parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts[:-1]) + "Z")
    return "".join(parts), best[1]


def _leaders(items):
    """Espalha os rótulos de chamada na margem direita sem sobrepor."""
    items.sort(key=lambda it: it["ly"])
    last = -1e9
    for it in items:
        it["ty"] = round(max(it["ly"], last + 15), 1)
        last = it["ty"]
        it["tx"] = MAP_W + 8


def geo_payload(geo_dir, biomes, ufs):
    geo_dir = Path(geo_dir)
    bj = json.loads((geo_dir / "biomas.geojson").read_text(encoding="utf-8"))
    uj = json.loads((geo_dir / "ufs.geojson").read_text(encoding="utf-8"))
    by_cd = {f["properties"]["cd"]: f for f in bj["features"]}
    by_sigla = {f["properties"]["sigla"]: f for f in uj["features"]}
    out_b, out_u = [], []
    for k, name in enumerate(biomes):
        d, (lx, ly) = _feature_svg(by_cd[BIOME_CD[name]]["geometry"])
        out_b.append({"k": k, "d": d, "lx": round(lx, 1), "ly": round(ly, 1), "lead": name in LEAD_BIOME})
    for k, u in enumerate(ufs):
        d, (lx, ly) = _feature_svg(by_sigla[u["sigla"]]["geometry"])
        out_u.append({"k": k, "d": d, "lx": round(lx, 1), "ly": round(ly, 1), "lead": u["sigla"] in LEAD_UF})
    _leaders([b for b in out_b if b["lead"]])
    _leaders([u for u in out_u if u["lead"]])
    ys = [float(v) for f in out_b for v in f["d"].replace("M", " ").replace("L", " ").replace("Z", " ").split()[1::2]]
    h = math.ceil(max(ys) + 4)
    return {"w": MAP_W + LEAD_W, "mw": MAP_W, "h": h, "biomes": out_b, "ufs": out_u}


def write(payload, geo_dir, out_path, build_date, dashboard_href="index.html"):
    import site_header as sh
    data = {k: payload[k] for k in ("months", "biomes", "ufs", "classes", "facts", "cover")}
    data["geo"] = geo_payload(geo_dir, payload["biomes"], payload["ufs"])
    html = (TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            .replace("__BUILD_DATE__", build_date).replace("__DASH__", dashboard_href))
    pages = [(dashboard_href + "#painel", "Painel", "tabPainel"), (dashboard_href + "#metodo", "Método", "tabMetodo"),
             ("destaques.html", "Destaques do mês", "tabDestaques")]
    html = (html.replace("__SITE_HEAD__", sh.JS_HEAD).replace("__SITE_CSS__", sh.CSS)
            .replace("__SITE_HEADER__", sh.html(pages, "tabDestaques")).replace("__SITE_JS__", sh.JS_BODY)
            .replace("__LOGOS__", sh.logos_html().replace("'", "\'")))
    Path(out_path).write_text(html, encoding="utf-8")
    return len(html)


TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__SITE_HEAD__
<title>Destaques do mês</title>
<meta name="description" content="Destaques mensais do fogo no Brasil: área queimada do MapBiomas Monitor do Fogo e as emissões estimadas dessa área.">
<style>
:root {
  --page: #f3ede2; --surface: #fbf8f2; --ink: #2a2119; --ink-2: #5b4a3b; --muted: #7d6b58;
  --line: #e6dccb; --grid: #e6dccb; --axis: #cbbca4; --soft: #f0e8da; --bar: #cfc4b4; --nodata: #ebe4d8;
  --accent: #9a4f26; --accent-weak: #ecd8c6; --on-accent: #fbf8f2;
  --area: #d23b25; --emis: #4b3f8f; --up: #b3261e; --down: #1f7a3f; --nat: #1f8d49; --ant: #f6ecc4;
}
:root[data-theme="dark"] {
  --page: #16120e; --surface: #201b16; --ink: #f2ece2; --ink-2: #cdbfac; --muted: #9c8c78;
  --line: #3a3128; --grid: #2f2821; --axis: #463b30; --soft: #2a231c; --bar: #5a4e42; --nodata: #2e2720;
  --accent: #d98c5f; --accent-weak: #4d3222; --on-accent: #16120e;
  --area: #ec6a52; --emis: #9585e6; --up: #e66767; --down: #4cbf72; --nat: #2fa35c; --ant: #e8d9a8;
}
* { box-sizing: border-box; }
html { background: var(--page); }
body { margin: 0; background: var(--page); color: var(--ink); font: 14px/1.45 "Montserrat", "Segoe UI", system-ui, -apple-system, sans-serif;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.tools { max-width: 1240px; margin: 0 auto; padding: 14px 16px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.tools label { font-size: 12px; font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.tools select, .tools button, .tools nav a { font: inherit; font-size: 13px; border-radius: 999px; padding: 6px 13px; border: 1px solid var(--axis);
  background: var(--surface); color: var(--ink); text-decoration: none; cursor: pointer; }
.tools nav { display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }
.tools nav a { padding: 4px 11px; font-size: 12.5px; color: var(--ink-2); }
.tools nav a:hover { background: var(--accent-weak); }
.tools select:focus-visible, .tools button:focus-visible, .tools nav a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
main { max-width: 1240px; margin: 0 auto; padding: 18px 16px 40px; }
.pg { background: var(--surface); border-radius: 14px; padding: 26px 34px 18px; margin-bottom: 22px; box-shadow: 0 1px 2px rgba(40,30,20,.08); display: flex; flex-direction: column; }
.ph { display: flex; align-items: center; gap: 16px; border-bottom: 3px solid var(--area); padding-bottom: 12px; margin-bottom: 14px; }
.ph .site-logos .mbf { height: 22px; } .ph .site-logos .ipam { height: 30px; }
.ph .brand { font-weight: 600; font-size: 15px; line-height: 1.15; color: var(--ink-2); }
.ph .brand small { display: block; font-weight: 500; color: var(--muted); font-size: 12px; }
.ph .tag { color: var(--area); font-weight: 800; font-size: 20px; letter-spacing: .03em; border-left: 3px solid var(--area); border-right: 3px solid var(--area); padding: 2px 16px; }
.ph .when { margin-left: auto; font-weight: 800; font-size: 16px; letter-spacing: .03em; }
.kick { color: var(--area); font-weight: 800; font-size: 12px; letter-spacing: .1em; text-transform: uppercase; }
h1 { font-size: 26px; margin: 2px 0 6px; line-height: 1.2; }
h2 { font-size: 20px; margin: 2px 0 4px; line-height: 1.25; }
h3 { font-size: 15px; margin: 18px 0 2px; }
.lead { color: var(--ink-2); margin: 0 0 14px; font-size: 14.5px; max-width: 980px; }
.sub { color: var(--muted); font-size: 12.5px; margin: 0 0 6px; }
.cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 28px; }
.cols > * { min-width: 0; }
.kcard { border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; box-shadow: 0 2px 6px rgba(40,30,20,.06); }
.kpair > *, .ch2 > *, .bigpair > * { min-width: 0; }
.kpair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.kl { font-size: 11.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-2); }
.k { padding-left: 10px; border-left: 4px solid var(--area); }
.k.e { border-left-color: var(--emis); }
.kv { font-size: clamp(22px, 2.5vw, 31px); font-weight: 800; line-height: 1.1; margin: 4px 0 2px; letter-spacing: -.01em; white-space: nowrap; }
.kv u { text-decoration: none; font-size: 15px; font-weight: 700; margin-left: 4px; }
.share { font-size: 12.5px; font-weight: 600; color: var(--ink-2); margin: 2px 0 4px; }
ul.dl { list-style: none; padding: 0; margin: 4px 0 0; font-size: 12.5px; color: var(--ink-2); }
ul.dl li { margin: 2px 0; }
ul.dl b { font-weight: 800; font-size: 14px; }
ul.dl .up b, ul.dl .up i { color: var(--up); } ul.dl .down b, ul.dl .down i { color: var(--down); }
ul.dl i { font-style: normal; font-size: 11px; margin-right: 2px; }
ul.dl small { color: var(--muted); font-size: 11px; white-space: nowrap; }
.chips { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
.chip { background: var(--soft); border-radius: 10px; padding: 8px 12px; font-size: 12px; color: var(--ink-2); flex: 1 1 160px; }
.chip .ct { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; color: var(--ink-2); }
.chip .cv { font-size: 19px; font-weight: 800; color: var(--ink); line-height: 1.2; }
.ch2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; margin-top: 12px; }
figure { margin: 0; min-width: 0; }
figcaption { font-size: 13px; font-weight: 700; }
figcaption span { display: block; font-weight: 400; font-size: 11.5px; color: var(--muted); }
svg { display: block; width: 100%; height: auto; overflow: visible; }
svg text { font-family: inherit; }
.cov { margin-top: 4px; }
.covrow { display: grid; grid-template-columns: 62px minmax(0, 1fr); gap: 8px; align-items: center; margin: 6px 0; }
.covrow .lab { font-size: 12px; font-weight: 700; color: var(--ink-2); }
.tiers { position: relative; }
.t1, .t2 { display: flex; height: 22px; border-radius: 5px; overflow: hidden; gap: 2px; background: var(--surface); }
.t2 { margin-top: 3px; }
.t1 span, .t2 span { display: flex; align-items: center; justify-content: center; font-size: 11.5px; font-weight: 700; min-width: 0; overflow: hidden; white-space: nowrap; }
.t1 .n { background: var(--nat); color: #fff; } .t1 .a { background: var(--ant); color: #2a2119; box-shadow: inset 0 0 0 1px #e2d29a; }
.tiers .div { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--ink); }
.leg { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 11.5px; color: var(--ink-2); margin-top: 8px; }
.leg i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }
.mapgrid { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); gap: 26px; align-items: start; }
.mapgrid > * { min-width: 0; }
.mapwrap { position: relative; }
.mapwrap .tog { display: flex; gap: 4px; justify-content: center; margin: 4px 0 6px; }
.tog button { font: inherit; font-size: 12px; border: 1px solid var(--line); background: var(--surface); color: var(--ink-2); border-radius: 999px; padding: 4px 12px; cursor: pointer; }
.tog button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--surface); font-weight: 600; }
.tog button:focus-visible { outline: 2px solid var(--emis); outline-offset: 2px; }
.mleg { font-size: 11.5px; color: var(--ink-2); margin-top: 4px; }
.mleg b { display: block; font-size: 12px; margin-bottom: 3px; color: var(--ink); }
.mleg div { display: flex; align-items: center; gap: 6px; margin: 1px 0; }
.mleg i { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
.callout { width: 150px; height: 150px; border-radius: 50%; background: #4b3f8f; color: #fff; display: flex; align-items: center; justify-content: center; text-align: center;
  font-weight: 800; font-size: 13px; line-height: 1.25; padding: 18px; text-transform: uppercase; box-shadow: 0 8px 24px rgba(75,63,143,.3); flex: none; }
.callout.sm { width: 92px; height: 92px; font-size: 11.5px; padding: 10px; }
.mapfoot { display: flex; gap: 18px; align-items: flex-end; justify-content: space-between; margin-top: 6px; }
.big { white-space: nowrap; font-size: clamp(24px, 2.7vw, 36px); font-weight: 800; line-height: 1.05; letter-spacing: -.01em; }
.big u { text-decoration: none; font-size: 16px; margin-left: 4px; }
.bigpair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
.rk { display: grid; grid-template-columns: minmax(84px, auto) minmax(0, 1fr) minmax(0, 1fr) 64px; gap: 6px 10px; align-items: center; font-size: 12px; margin-top: 8px; }
.rk .h { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 700; border-bottom: 1px solid var(--line); padding-bottom: 4px; }
.rk .h.r, .rk .r { text-align: right; }
.rk .nm { color: var(--ink-2); text-align: right; white-space: nowrap; }
.rk .cell { display: flex; align-items: center; gap: 6px; min-width: 0; }
.rk .cell i { display: block; height: 16px; border-radius: 0 4px 4px 0; flex: none; min-width: 2px; }
.rk .cell span { font-weight: 700; color: var(--ink-2); white-space: nowrap; font-size: 11.5px; }
.rk .cell span small { font-weight: 500; color: var(--muted); }
.rk.one { grid-template-columns: minmax(70px, auto) minmax(0, 1fr); }
.track { position: relative; height: 16px; }
.track i { position: absolute; left: 0; top: 0; bottom: 0; background: var(--emis); border-radius: 0 4px 4px 0; }
.track b { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--ink); }
.side { display: flex; flex-direction: column; gap: 10px; }
.sidehead { display: flex; gap: 14px; align-items: center; }
.note { font-size: 12px; color: var(--muted); }
.src { margin-top: auto; padding-top: 14px; border-top: 1px solid var(--line); font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; gap: 16px; }
.cmp { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 6px; font-variant-numeric: tabular-nums; }
.cmp th, .cmp td { padding: 5px 8px; border-bottom: 1px solid var(--line); text-align: right; }
.cmp th:first-child, .cmp td:first-child { text-align: left; }
.cmp th { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.gasbar { display: flex; height: 26px; border-radius: 6px; overflow: hidden; gap: 2px; margin-top: 6px; }
.gasbar span { display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11.5px; font-weight: 700; white-space: nowrap; overflow: hidden; }
.dtop { display: grid; grid-template-columns: minmax(0, 1.25fr) 170px minmax(0, 1fr); gap: 24px; align-items: start; margin-bottom: 16px; }
.dtop > * { min-width: 0; }
.ck { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 28px; }
.ck > * { min-width: 0; }
@media (max-width: 980px) {
  .cols, .mapgrid, .ck, .dtop { grid-template-columns: minmax(0, 1fr); }
  .loc { max-width: 220px; }
  .pg { padding: 18px 16px 14px; }
}
@media (max-width: 560px) {
  .kpair, .ch2, .bigpair { grid-template-columns: minmax(0, 1fr); }
  .rk.r4 { grid-template-columns: minmax(56px, auto) minmax(0, 1fr) minmax(0, 1fr); gap: 6px; }
  .rk .h.hide, .rk .hide { display: none; }
  .ph { flex-wrap: wrap; } .ph .tag { font-size: 16px; }
  h1 { font-size: 21px; }
  .kv, .big { white-space: normal; font-size: 24px; }
  .ph .when { margin-left: 0; }
  .chip { flex-basis: 100%; }
}
__SITE_CSS__
@page { size: A4 landscape; margin: 7mm; }
@media print {
  html, body { background: #fff; }
  .tools, .tog { display: none !important; }
  main { padding: 0; max-width: none; }
  .pg { box-shadow: none; border-radius: 0; margin: 0; padding: 0; break-after: page; width: 1500px; zoom: .7; }
  .pg:last-child { break-after: auto; }
  .cols, .mapgrid, .ck { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important; }
  .kpair, .ch2, .bigpair { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important; }
  .dtop { grid-template-columns: minmax(0, 1.25fr) 150px minmax(0, 1fr) !important; margin-bottom: 8px; }
  .mapgrid svg { max-height: 600px; }
  .rk.r4 { grid-template-columns: minmax(84px, auto) minmax(0, 1fr) minmax(0, 1fr) 64px !important; }
  .rk.r4 .hide { display: block !important; }
  h3 { margin-top: 12px; }
}
</style>
</head>
<body>
__SITE_HEADER__
<div class="tools">
  <label for="selM">Mês</label><select id="selM"></select>
  <button type="button" id="btnPrint">Imprimir ou salvar PDF</button>
  <nav aria-label="Seções"><a href="#p1">Brasil</a><a href="#p2">Biomas</a><a href="#p3">Bioma</a><a href="#p4">Estados</a><a href="#p5">Estado</a><a href="#p6">Área × emissão</a></nav>
</div>
<main id="main"></main>
<script>
const DATA = __DATA__;
const BUILD = '__BUILD_DATE__';
const $ = id => document.getElementById(id);
const F = DATA.facts, N = F.m.length, MONTHS = DATA.months, NM = MONTHS.length;
const BIOMES = DATA.biomes, NB = BIOMES.length, UFS = DATA.ufs, NU = UFS.length, G = DATA.geo;
const MES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const MES3 = MES.map(m => m.slice(0, 3));
const UF_NAME = UFS.map(u => u.nome);

// ---------- coberturas: nativas primeiro, depois agropecuária ----------
const ORDER = ['Formação Florestal', 'Formação Savânica', 'Formação Campestre', 'Campo Alagado e Área Pantanosa',
  'Pastagem', 'Agricultura', 'Mosaico de Usos', 'Silvicultura'];
const COLOR = Object.fromEntries(DATA.cover);
const GROUPS = [...ORDER.filter(n => DATA.classes.some(c => c['Nível 1_1'] === n)),
  ...[...new Set(DATA.classes.map(c => c['Nível 1_1']))].filter(n => !ORDER.includes(n))];
const NG = GROUPS.length;
const CL_G = DATA.classes.map(c => GROUPS.indexOf(c['Nível 1_1']));
const CL_NAT = DATA.classes.map(c => c['Nível 0'] === 'Natural');
const G_NAT = GROUPS.map((_, g) => DATA.classes.some((c, i) => CL_G[i] === g && CL_NAT[i]));
const gColor = g => COLOR[GROUPS[g]] || '#9c8f80';

// ---------- índice por mês e soma de um conjunto de meses num recorte ----------
const BY_M = Array.from({ length: NM }, () => []);
for (let i = 0; i < N; i++) BY_M[F.m[i]].push(i);
const mIdx = (y, mo) => MONTHS.indexOf(y + '-' + String(mo).padStart(2, '0'));
function months(y, mo, acc) { const out = []; for (let k = acc ? 1 : mo; k <= mo; k++) { const i = mIdx(y, k); if (i >= 0) out.push(i); } return out; }
function sum(ms, b = -1, u = -1) {
  const r = { A: 0, E: 0, nA: 0, nE: 0, gA: new Float64Array(NG), gE: new Float64Array(NG),
    bA: new Float64Array(NB), bE: new Float64Array(NB), uA: new Float64Array(NU), uE: new Float64Array(NU), gas: [0, 0, 0] };
  for (const m of ms) for (const i of BY_M[m]) {
    if (b >= 0 && F.b[i] !== b) continue;
    if (u >= 0 && F.u[i] !== u) continue;
    const a = F.a[i], e = F.co2[i] + F.ch4[i] + F.n2o[i], c = F.c[i], g = CL_G[c];
    r.A += a; r.E += e; if (CL_NAT[c]) { r.nA += a; r.nE += e; }
    r.gA[g] += a; r.gE[g] += e; r.bA[F.b[i]] += a; r.bE[F.b[i]] += e; r.uA[F.u[i]] += a; r.uE[F.u[i]] += e;
    r.gas[0] += F.co2[i]; r.gas[1] += F.ch4[i]; r.gas[2] += F.n2o[i];
  }
  return r;
}

// ---------- formatação (pt-BR; área sempre em ha, quantidades em t) ----------
const NF = {}; const nf = d => NF[d] || (NF[d] = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }));
const int = v => nf(0).format(Math.round(v));
const pct = (v, t) => t > 0 ? v / t * 100 : 0;
const pctTxt = p => p > 0 && p < 1 ? '<1%' : nf(0).format(p) + '%';
const signed = (v, d = 0) => (v >= 0 ? '+' : '−') + nf(d).format(Math.abs(v));
function words(v, unit) {  // 799 mil ha · 1,8 milhão de ha · 106,4 milhões de t CO₂e
  const a = Math.abs(v), s = v < 0 ? '−' : '';
  if (a >= 1e9) return s + nf(1).format(a / 1e9) + (a < 2e9 ? ' bilhão de ' : ' bilhões de ') + unit;
  if (a >= 1e6) return s + nf(1).format(a / 1e6).replace(/,0$/, '') + (a < 2e6 ? ' milhão de ' : ' milhões de ') + unit;
  if (a >= 1e3) return s + int(a / 1e3) + ' mil ' + unit;
  return s + int(a) + ' ' + unit;
}
const wshort = (v, unit) => { const a = Math.abs(v), s = v < 0 ? '−' : '';  // forma curta para as variações
  return a >= 1e6 ? s + nf(1).format(a / 1e6).replace(/,0$/, '') + ' mi ' + unit : a >= 1e3 ? s + int(a / 1e3) + ' mil ' + unit : s + int(a) + ' ' + unit; };
const mapNum = v => v >= 1e3 ? int(v / 1e3) + ' mil' : int(v);
const UA = 'ha', UE = 't CO₂e';
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// ---------- pequenos componentes ----------
function deltaLi(cur, ref, unit, label) {
  if (!(ref > 0)) return '';
  const p = (cur / ref - 1) * 100, up = p >= 0;
  return '<li class="' + (up ? 'up' : 'down') + '"><i>' + (up ? '▲' : '▼') + '</i><b>' + signed(p) + '%</b> vs. ' + esc(label)
    + ' <small>(' + (up ? '+' : '') + wshort(cur - ref, unit) + ')</small></li>';
}
function niceMax(v) { if (!(v > 0)) return 1; const e = Math.pow(10, Math.floor(Math.log10(v))), f = v / e; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e; }
function scaleOf(max, unit) { return max >= 1e6 ? [1e6, 'milhões de ' + unit, 1] : max >= 1e3 ? [1e3, 'mil ' + unit, 0] : [1, unit, 0]; }

// barras por ano: cinza nos anos anteriores, cor no ano do destaque, linha tracejada da média
function yearBars(vals, years, color, unit, aria) {
  const W = 340, H = 196, L = 30, Rm = 64, T = 18, B = 26, pw = W - L - Rm, ph = H - T - B;
  const prev = vals.slice(0, -1).filter(v => v > 0), mean = prev.length ? prev.reduce((s, v) => s + v, 0) / prev.length : null;
  const [div, lab, dec] = scaleOf(Math.max(...vals, mean || 0), unit);
  const top = niceMax(Math.max(...vals, mean || 0) / div), y = v => T + ph - v / div / top * ph;
  const slot = pw / vals.length, bw = Math.min(30, slot * 0.64);
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(aria) + '">';
  for (let k = 0; k <= 4; k++) { const v = top * k / 4, yy = T + ph - ph * k / 4;
    s += '<line x1="' + L + '" x2="' + (L + pw) + '" y1="' + yy + '" y2="' + yy + '" stroke="var(--grid)"/>';
    s += '<text x="' + (L - 6) + '" y="' + (yy + 3.5) + '" font-size="9.5" fill="var(--muted)" text-anchor="end">' + nf(Number.isInteger(Math.round(v * 100) / 100) ? 0 : (Math.round(v * 10) / 10 === v ? 1 : 2)).format(v) + '</text>'; }
  vals.forEach((v, i) => {
    const x = L + slot * i + (slot - bw) / 2, last = i === vals.length - 1, h = Math.max(0, T + ph - y(v)), yy = y(v);
    s += '<path d="M' + x + ' ' + (T + ph) + 'V' + (yy + Math.min(3, h)) + 'q0 -' + Math.min(3, h) + ' ' + Math.min(3, h) + ' -' + Math.min(3, h) + 'H' + (x + bw - Math.min(3, h)) + 'q' + Math.min(3, h) + ' 0 ' + Math.min(3, h) + ' ' + Math.min(3, h) + 'V' + (T + ph) + 'Z" fill="' + (last ? color : 'var(--bar)') + '"><title>' + years[i] + ': ' + int(v) + ' ' + unit + '</title></path>';
    s += '<text x="' + (x + bw / 2) + '" y="' + (yy - 5) + '" font-size="' + (last ? 10.5 : 9.5) + '" font-weight="' + (last ? 800 : 600) + '" fill="' + (last ? color : 'var(--ink-2)') + '" text-anchor="middle">' + nf(dec || v / div < 10 ? 1 : 0).format(v / div) + '</text>';
    s += '<text x="' + (x + bw / 2) + '" y="' + (H - 9) + '" font-size="9.5" fill="' + (last ? color : 'var(--muted)') + '" font-weight="' + (last ? 700 : 400) + '" text-anchor="middle">' + years[i] + '</text>';
  });
  if (mean !== null) { const ym = y(mean);
    s += '<line x1="' + L + '" x2="' + (L + pw + 4) + '" y1="' + ym + '" y2="' + ym + '" stroke="var(--ink)" stroke-dasharray="4 3" stroke-width="1.2"/>';
    s += '<text x="' + (L + pw + 7) + '" y="' + (ym - 3) + '" font-size="9.5" fill="var(--ink-2)">média</text>';
    s += '<text x="' + (L + pw + 7) + '" y="' + (ym + 9) + '" font-size="10" font-weight="800" fill="var(--ink)">' + nf(mean / div < 10 ? 1 : 0).format(mean / div) + '</text>'; }
  return [s + '</svg>', lab];
}

// duas faixas: nativa × agropecuária e as coberturas
const inkOn = hex => { const n = parseInt(hex.slice(1), 16), r = n >> 16, g = n >> 8 & 255, b = n & 255; return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#1f1a15' : '#fff'; };
function tiers(vals, nat, total) {
  if (!(total > 0)) return '<div class="note">sem área queimada</div>';
  const pn = pct(nat, total), pa = 100 - pn;
  let t2 = '';
  GROUPS.forEach((n, g) => { const p = pct(vals[g], total); if (p <= 0) return;
    const c = gColor(g); t2 += '<span style="flex:' + p + ';background:' + c + ';color:' + inkOn(c) + '" title="' + esc(n) + ': ' + pctTxt(p) + '">' + (p >= 7 ? nf(0).format(p) + '%' : '') + '</span>'; });
  return '<div class="tiers"><div class="t1">' + (pn > 0 ? '<span class="n" style="flex:' + pn + '">' + (pn >= 6 ? nf(0).format(pn) + '%' : '') + '</span>' : '')
    + (pa > 0.05 ? '<span class="a" style="flex:' + pa + '">' + (pa >= 6 ? nf(0).format(pa) + '%' : '') + '</span>' : '') + '</div>'
    + '<div class="t2">' + t2 + '</div><div class="div" style="left:calc(' + pn + '% - 1px)"></div></div>';
}
function coverBlock(r, title) {
  const present = GROUPS.map((n, g) => [n, g]).filter(([, g]) => r.gA[g] > 0 || r.gE[g] > 0);
  return '<h3>' + esc(title) + '</h3><p class="sub">Linha de cima: vegetação nativa × agropecuária · linha de baixo: cada cobertura · % do total de cada medida</p><div class="cov">'
    + '<div class="covrow"><span class="lab">Área</span>' + tiers(r.gA, r.nA, r.A) + '</div>'
    + '<div class="covrow"><span class="lab">Emissão</span>' + tiers(r.gE, r.nE, r.E) + '</div></div>'
    + '<div class="leg"><span><i style="background:var(--nat)"></i>Nativa</span><span><i style="background:var(--ant);box-shadow:inset 0 0 0 1px #d8c78a"></i>Agropecuária</span>'
    + present.map(([n, g]) => '<span><i style="background:' + gColor(g) + '"></i>' + esc(n) + '</span>').join('') + '</div>';
}

// ---------- coluna de período (mês ou acumulado) ----------
function periodCol(ctx, acc, b = -1, u = -1, scopeName = null) {
  const { y, mo, years } = ctx, lab = acc ? 'jan–' + MES3[mo - 1] : MES[mo - 1];
  const per = years.map(yy => sum(months(yy, mo, acc), b, u));
  const cur = per[per.length - 1], prev = per.length > 1 ? per[per.length - 2] : null;
  const old = per.slice(0, -1), avg = k => old.length ? old.reduce((s, r) => s + r[k], 0) / old.length : null;
  const br = scopeName ? sum(months(y, mo, acc)) : null;
  const mean = 'média ' + years[0] + '–' + (y - 1), pl = (acc ? 'jan–' + MES3[mo - 1] + ' de ' : MES[mo - 1] + ' de ') + (y - 1);
  const head = acc ? 'Acumulado de jan–' + MES3[mo - 1] + ' de ' + y : 'Em ' + MES[mo - 1] + ' de ' + y;
  const kp = (cls, kl, v, unit, key, shareKey) => '<div class="k ' + cls + '"><div class="kl">' + kl + '</div><div class="kv">' + int(v) + '<u>' + unit + '</u></div>'
    + (br ? '<div class="share">' + pctTxt(pct(v, br[shareKey])) + ' do Brasil ' + (acc ? 'no ano' : 'no mês') + '</div>' : '')
    + '<ul class="dl">' + (prev ? deltaLi(v, prev[key], unit, pl) : '') + deltaLi(v, avg(key), unit, mean) + '</ul></div>';
  const ints = cur.A > 0 ? cur.E / cur.A : 0, intsAvg = avg('A') > 0 ? avg('E') / avg('A') : null;
  let chip3 = '';
  if (acc) {
    const ms = months(y, mo, true), byM = ms.map(m => sum([m], b, u)), k = byM.reduce((bi, r, i) => r.E > byM[bi].E ? i : bi, 0);
    chip3 = '<div class="chip"><div class="ct">Mês de maior emissão</div><div class="cv">' + MES[k][0].toUpperCase() + MES[k].slice(1) + '</div>'
      + words(byM[k].E, UE) + ' · ' + pctTxt(pct(byM[k].E, cur.E)) + ' do acumulado</div>';
  } else {
    chip3 = '<div class="chip"><div class="ct">Vegetação nativa</div><div class="cv">' + pctTxt(pct(cur.nE, cur.E)) + ' da emissão</div>'
      + pctTxt(pct(cur.nA, cur.A)) + ' da área queimada</div>';
  }
  const [svA, labA] = yearBars(per.map(r => r.A), years, 'var(--area)', UA, 'Área queimada ' + (acc ? 'de jan a ' + MES[mo - 1] : 'em ' + MES[mo - 1]) + ' por ano');
  const [svE, labE] = yearBars(per.map(r => r.E), years, 'var(--emis)', UE, 'Emissão ' + (acc ? 'de jan a ' + MES[mo - 1] : 'em ' + MES[mo - 1]) + ' por ano');
  return '<div><div class="kcard"><div class="kl" style="margin-bottom:8px;font-weight:700">' + esc(head) + '</div><div class="kpair">'
    + kp('a', 'Área queimada', cur.A, UA, 'A', 'A') + kp('e', 'Emissão', cur.E, UE, 'E', 'E') + '</div>'
    + '<div class="chips"><div class="chip"><div class="ct">Emissão por ha queimado</div><div class="cv">' + nf(1).format(ints) + ' t CO₂e/ha</div>'
    + (intsAvg ? mean + ': ' + nf(1).format(intsAvg) + ' t CO₂e/ha' : '') + '</div>' + chip3 + '</div></div>'
    + '<div class="ch2"><figure><figcaption>Área queimada ' + (acc ? 'de jan a ' + MES[mo - 1] : 'em ' + MES[mo - 1]) + ', por ano<span>em ' + labA + '</span></figcaption>' + svA + '</figure>'
    + '<figure><figcaption>Emissão ' + (acc ? 'de jan a ' + MES[mo - 1] : 'em ' + MES[mo - 1]) + ', por ano<span>em ' + labE + '</span></figcaption>' + svE + '</figure></div>'
    + coverBlock(cur, 'Uso e cobertura (' + lab + (acc ? ' de ' : ' de ') + y + ')') + '</div>';
}

// ---------- mapas ----------
const RAMP = { E: ['#ebe7f5', '#c6bce4', '#9888cc', '#6a55b0', '#3c2b80'], A: ['#fde4dc', '#f6b4a3', '#ec7b61', '#d6432a', '#9f2018'] };
function breaks(vals) {
  const v = vals.filter(x => x > 0).sort((a, b) => a - b); if (!v.length) return [];
  const q = [0.2, 0.4, 0.6, 0.8].map(p => v[Math.min(v.length - 1, Math.floor(p * v.length))]);
  return [...new Set([v[0], ...q, v[v.length - 1]])];
}
function classOf(x, br) { if (!(x > 0)) return -1; for (let k = 1; k < br.length; k++) if (x <= br[k]) return k - 1; return br.length - 2; }
function choropleth(kind, vals, total, key, aria) {
  const feats = kind === 'b' ? G.biomes : G.ufs, br = breaks(vals), nCls = Math.max(1, br.length - 1);
  const ramp = RAMP[key], col = k => ramp[Math.round(k * (ramp.length - 1) / Math.max(1, nCls - 1))];
  let s = '<svg viewBox="0 0 ' + G.w + ' ' + G.h + '" role="img" aria-label="' + esc(aria) + '">', lab = '';
  feats.forEach(f => { const v = vals[f.k], k = br.length > 1 ? classOf(v, br) : (v > 0 ? 0 : -1), name = kind === 'b' ? BIOMES[f.k] : UFS[f.k].sigla;
    const fill = k < 0 ? 'var(--nodata)' : col(k);
    s += '<path d="' + f.d + '" fill="' + fill + '" stroke="var(--surface)" stroke-width="' + (kind === 'b' ? 1.4 : 0.9) + '" stroke-linejoin="round"><title>' + esc(kind === 'b' ? name : UF_NAME[f.k]) + ': ' + int(v) + ' ' + (key === 'E' ? UE : UA) + ' · ' + pctTxt(pct(v, total)) + '</title></path>';
    const p = pct(v, total), ink = k >= 3 ? '#fff' : '#1f1a15';
    if (f.lead) {
      s += '<polyline points="' + f.lx + ',' + f.ly + ' ' + (G.mw - 4) + ',' + f.ty + ' ' + f.tx + ',' + f.ty + '" fill="none" stroke="var(--ink)" stroke-width=".7"/><circle cx="' + f.lx + '" cy="' + f.ly + '" r="1.8" fill="var(--ink)"/>';
      lab += '<text x="' + (f.tx + 3) + '" y="' + (f.ty + 3.5) + '" font-size="10.5" fill="var(--ink)"><tspan font-weight="800">' + esc(name) + '</tspan> ' + mapNum(v) + (p >= 1 ? ' · ' + pctTxt(p) : '') + '</text>';
    } else {
      const big = kind === 'b' || p >= 3;
      lab += '<text x="' + f.lx + '" y="' + (f.ly - (big ? 4 : 0)) + '" font-size="' + (kind === 'b' ? 12 : 10.5) + '" font-weight="800" fill="' + ink + '" text-anchor="middle">' + esc(name) + '</text>'
        + '<text x="' + f.lx + '" y="' + (f.ly + (big ? 8 : 11)) + '" font-size="9.5" fill="' + ink + '" text-anchor="middle">' + mapNum(v) + '</text>'
        + (big ? '<text x="' + f.lx + '" y="' + (f.ly + 19) + '" font-size="9.5" fill="' + ink + '" text-anchor="middle">' + pctTxt(p) + '</text>' : '');
    }
  });
  s += lab + '</svg>';
  let lg = '';
  for (let k = 0; k < nCls && br.length > 1; k++) lg += '<div><i style="background:' + col(k) + '"></i>' + mapNum(br[k]) + ' – ' + mapNum(br[k + 1]) + '</div>';
  if (br.length === 1) lg += '<div><i style="background:' + col(0) + '"></i>' + mapNum(br[0]) + '</div>';
  lg += '<div><i style="background:var(--nodata)"></i>sem área queimada</div>';
  return [s, lg];
}
function locator(kind, k) {
  const feats = kind === 'b' ? G.biomes : G.ufs;
  let s = '<svg viewBox="0 0 ' + G.mw + ' ' + G.h + '" role="img" aria-label="Localização">';
  if (kind === 'u') G.biomes.forEach(f => { s += '<path d="' + f.d + '" fill="none"/>'; });
  feats.forEach(f => { s += '<path d="' + f.d + '" fill="' + (f.k === k ? 'var(--emis)' : 'var(--nodata)') + '" stroke="var(--surface)" stroke-width="1"/>'; });
  return s + '</svg>';
}

// ranking com área e emissão lado a lado
function ranking(names, A, E, totA, totE, top, full = n => n) {
  const idx = [...names.keys()].filter(k => A[k] > 0 || E[k] > 0).sort((a, b) => E[b] - E[a]).slice(0, top);
  const mA = Math.max(...idx.map(k => A[k]), 1), mE = Math.max(...idx.map(k => E[k]), 1);
  let s = '<div class="rk r4"><span class="h"></span><span class="h">Área queimada (ha)</span><span class="h">Emissão (t CO₂e)</span><span class="h r hide">t CO₂e/ha</span>';
  idx.forEach(k => {
    s += '<span class="nm" title="' + esc(full(k)) + '">' + esc(names[k]) + '</span>'
      + '<span class="cell"><i style="width:' + (A[k] / mA * 44) + '%;background:var(--area)"></i><span>' + int(A[k]) + ' <small>· ' + pctTxt(pct(A[k], totA)) + '</small></span></span>'
      + '<span class="cell"><i style="width:' + (E[k] / mE * 44) + '%;background:var(--emis)"></i><span>' + int(E[k]) + ' <small>· ' + pctTxt(pct(E[k], totE)) + '</small></span></span>'
      + '<span class="r hide">' + (A[k] > 0 ? nf(1).format(E[k] / A[k]) : '—') + '</span>';
  });
  return [s + '</div>', idx];
}
function oneRank(names, V, tot, top, color, unit) {
  const idx = [...names.keys()].filter(k => V[k] > 0).sort((a, b) => V[b] - V[a]).slice(0, top), m = Math.max(...idx.map(k => V[k]), 1);
  return '<div class="rk one">' + idx.map(k => '<span class="nm">' + esc(names[k]) + '</span><span class="cell"><i style="width:' + (V[k] / m * 52) + '%;background:' + color + '"></i><span>'
    + int(V[k]) + ' <small>' + unit + ' · ' + pctTxt(pct(V[k], tot)) + '</small></span></span>').join('') + '</div>';
}

// ---------- páginas ----------
const LOGOS = '__LOGOS__';
function pageHead(ctx) { return '<div class="ph">' + LOGOS + '<div class="brand">Monitor de emissões<small>por fogo</small></div><div class="tag">DESTAQUES</div><div class="when">' + MES[ctx.mo - 1].toUpperCase() + ' ' + ctx.y + '</div></div>'; }
function foot(ctx, n, extra) {
  return '<div class="src"><span>Área queimada: MapBiomas Monitor do Fogo. Emissões: estimativa deste monitor a partir da área queimada, dos estoques de carbono e de fatores do IPCC. Dados até '
    + MES[ctx.lastMo - 1] + ' de ' + ctx.lastY + '.' + (extra ? ' ' + extra : '') + '</span><span>' + n + '/6</span></div>';
}
const cap = s => s[0].toUpperCase() + s.slice(1);
const MASC = new Set(['Cerrado', 'Pantanal', 'Pampa']);
const artB = n => MASC.has(n) ? 'O ' : 'A ', emB = n => MASC.has(n) ? 'no ' : 'na ';

function page1(ctx) {
  const { y, mo } = ctx, r = sum(months(y, mo, false));
  const lead = 'Em ' + MES[mo - 1] + ' de ' + y + ', o fogo atingiu ' + words(r.A, 'ha') + ' e emitiu cerca de ' + words(r.E, UE)
    + '. A vegetação nativa foi ' + pctTxt(pct(r.nA, r.A)) + ' da área queimada e ' + pctTxt(pct(r.nE, r.E)) + ' da emissão; em média, cada hectare queimado emitiu '
    + nf(1).format(r.A > 0 ? r.E / r.A : 0) + ' t CO₂e.';
  return '<section class="pg" id="p1">' + pageHead(ctx) + '<div class="kick">Brasil</div><h1>Destaques do fogo no Brasil em ' + MES[mo - 1] + ' de ' + y + '</h1>'
    + '<p class="lead">' + lead + '</p><div class="cols">' + periodCol(ctx, false) + periodCol(ctx, true) + '</div>'
    + foot(ctx, 1, 'Coberturas: MapBiomas.') + '</section>';
}

function mapPage(ctx, kind) {
  const { y, mo } = ctx, r = sum(months(y, mo, false)), isB = kind === 'b';
  const A = isB ? r.bA : r.uA, E = isB ? r.bE : r.uE;
  const names = isB ? BIOMES : UFS.map(u => u.nome), tag = isB ? 'biomas' : 'estados', id = isB ? 'p2' : 'p4';
  const [rk, idx] = ranking(names, A, E, r.A, r.E, isB ? 6 : 10, k => names[k]);
  const topE = idx[0], topA = [...names.keys()].sort((a, b) => A[b] - A[a])[0];
  const art = isB ? artB(BIOMES[topE]) : '';
  const who = isB ? art + BIOMES[topE] : UFS[topE].sigla;
  let callout = isB ? who + ' foi o bioma que mais emitiu' : '';
  let lead;
  if (isB) {
    const ints = [...names.keys()].filter(k => A[k] > 500).sort((a, b) => E[b] / A[b] - E[a] / A[a]);
    lead = cap(art.trim().toLowerCase() + ' ' + BIOMES[topE]).trim() + ' respondeu por ' + pctTxt(pct(E[topE], r.E)) + ' da emissão e ' + pctTxt(pct(A[topE], r.A)) + ' da área queimada no mês.'
      + (topA !== topE ? ' Em área, quem mais queimou foi ' + artB(BIOMES[topA]).trim().toLowerCase() + ' ' + BIOMES[topA] + '.' : '')
      + (ints.length ? ' Por hectare queimado, ' + artB(BIOMES[ints[0]]).trim().toLowerCase() + ' ' + BIOMES[ints[0]] + ' emitiu mais: ' + nf(1).format(E[ints[0]] / A[ints[0]]) + ' t CO₂e/ha, contra ' + nf(1).format(r.E / r.A) + ' na média do Brasil.' : '');
  } else {
    const t3 = idx.slice(0, 3), s3 = t3.reduce((s, k) => s + E[k], 0), s10 = idx.reduce((s, k) => s + E[k], 0);
    const nm = t3.map(k => UFS[k].nome);
    callout = nm.slice(0, -1).join(', ') + ' e ' + nm[nm.length - 1];
    lead = nm.slice(0, -1).join(', ') + ' e ' + nm[nm.length - 1] + ' somam ' + pctTxt(pct(s3, r.E)) + ' da emissão do país. Os ' + idx.length + ' primeiros estados somam ' + pctTxt(pct(s10, r.E)) + '.';
  }
  const [mE, lgE] = choropleth(kind, E, r.E, 'E', 'Emissão por ' + (isB ? 'bioma' : 'estado'));
  const [mA, lgA] = choropleth(kind, A, r.A, 'A', 'Área queimada por ' + (isB ? 'bioma' : 'estado'));
  return '<section class="pg" id="' + id + '">' + pageHead(ctx) + '<div class="mapgrid"><div class="mapwrap">'
    + '<h2 style="text-align:center">' + cap(tag) + ' que mais emitiram em ' + MES[mo - 1] + '</h2>'
    + '<div class="tog" role="group" aria-label="Colorir o mapa por"><button type="button" aria-pressed="true" data-k="E">Emissão</button><button type="button" aria-pressed="false" data-k="A">Área queimada</button></div>'
    + '<div data-map="E">' + mE + '</div><div data-map="A" hidden>' + mA + '</div>'
    + '<div class="mapfoot"><div class="callout">' + esc(callout) + '</div><div class="mleg" data-map="E"><b>Emissão em ' + MES[mo - 1] + ' de ' + y + ' (t CO₂e)</b>' + lgE + '</div>'
    + '<div class="mleg" data-map="A" hidden><b>Área queimada em ' + MES[mo - 1] + ' de ' + y + ' (ha)</b>' + lgA + '</div></div></div>'
    + '<div class="side"><div class="kl">Brasil · ' + MES[mo - 1] + ' de ' + y + '</div><div class="bigpair"><div class="k"><div class="kl">Área queimada</div><div class="big">' + int(r.A) + '<u>ha</u></div></div>'
    + '<div class="k e"><div class="kl">Emissão</div><div class="big">' + int(r.E) + '<u>t CO₂e</u></div></div></div>'
    + '<p class="lead" style="margin:4px 0 0">' + esc(lead) + '</p>'
    + '<h3 style="margin-top:6px">Ranking dos ' + tag + ' que mais emitiram</h3><p class="sub">' + cap(MES[mo - 1]) + ' de ' + y + ', ordenado pela emissão · ao lado de cada valor, a participação no total do Brasil</p>'
    + rk + '</div></div>' + foot(ctx, isB ? 2 : 4, 'Contornos: IBGE.') + '</section>';
}

function detailPage(ctx, kind) {
  const { y, mo } = ctx, r = sum(months(y, mo, false)), isB = kind === 'b';
  const E = isB ? r.bE : r.uE, k = [...E.keys()].sort((a, b) => E[b] - E[a])[0];
  const b = isB ? k : -1, u = isB ? -1 : k;
  const name = isB ? BIOMES[k] : UFS[k].nome, art = isB ? artB(name) : (['PA', 'AM', 'MA', 'MT', 'AC', 'AP', 'TO', 'PI', 'CE', 'RN', 'PR', 'RS', 'ES', 'RJ', 'DF'].includes(UFS[k].sigla) ? 'O ' : '');
  const ry = sum(months(y, mo, true)), sc = sum(months(y, mo, true), b, u);
  const sub = pctTxt(pct(E[k], r.E)) + ' da emissão do Brasil no mês e ' + pctTxt(pct(sc.E, ry.E)) + ' no ano.';
  const rm = sum(months(y, mo, false), b, u);
  const inner = isB ? oneRank(UFS.map(x => x.sigla), rm.uE, rm.E, 6, 'var(--emis)', 't CO₂e')
    : oneRank(BIOMES, rm.bE, rm.E, 6, 'var(--emis)', 't CO₂e');
  return '<section class="pg" id="' + (isB ? 'p3' : 'p5') + '">' + pageHead(ctx) + '<div class="dtop"><div class="sidehead"><div class="callout sm">' + esc(isB ? name : UFS[k].sigla) + '</div><div><div class="kick">' + (isB ? 'Bioma' : 'Estado') + ' que mais emitiu</div>'
    + '<h2>' + esc(art + name) + ' foi o ' + (isB ? 'bioma' : 'estado') + ' que mais emitiu em ' + MES[mo - 1] + '</h2><div class="note">' + sub + '</div></div></div>'
    + '<div class="loc">' + locator(kind, k) + '</div>'
    + '<div><h3 style="margin-top:0">Emissão por ' + (isB ? 'estado no bioma' : 'bioma no estado') + '</h3><p class="sub">' + cap(MES[mo - 1]) + ' de ' + y + ' · participação no total ' + (isB ? 'do bioma' : 'do estado') + '</p>' + inner + '</div></div>'
    + '<div class="cols">' + periodCol(ctx, false, b, u, name) + periodCol(ctx, true, b, u, name) + '</div>'
    + foot(ctx, isB ? 3 : 5, 'Coberturas: MapBiomas. Contornos: IBGE.') + '</section>';
}

function page6(ctx) {
  const { y, mo, years } = ctx, r = sum(months(y, mo, false)), ra = sum(months(y, mo, true));
  // intensidade por bioma: mês atual × média do mesmo mês nos anos anteriores
  const prev = years.slice(0, -1).map(yy => sum(months(yy, mo, false)));
  const pA = new Float64Array(NB), pE = new Float64Array(NB);
  prev.forEach(p => { for (let b = 0; b < NB; b++) { pA[b] += p.bA[b]; pE[b] += p.bE[b]; } });
  const rowsI = [...BIOMES.keys()].filter(b => r.bA[b] > 0).sort((a, b) => r.bE[b] / r.bA[b] - r.bE[a] / r.bA[a]);
  const maxI = Math.max(...rowsI.map(b => Math.max(r.bE[b] / r.bA[b], pA[b] > 0 ? pE[b] / pA[b] : 0)), 1);
  let int1 = '<div class="rk" style="grid-template-columns:minmax(96px,auto) 1fr auto">';
  rowsI.forEach(b => { const v = r.bE[b] / r.bA[b], m = pA[b] > 0 ? pE[b] / pA[b] : null;
    int1 += '<span class="nm">' + esc(BIOMES[b]) + '</span><span class="track"><i style="width:' + (v / maxI * 100) + '%"></i>'
      + (m ? '<b style="left:calc(' + (m / maxI * 100) + '% - 1px)" title="média do mesmo mês ' + years[0] + '–' + (y - 1) + '"></b>' : '') + '</span>'
      + '<span class="r"><b>' + nf(1).format(v) + '</b>' + (m ? ' <small class="note">média ' + nf(1).format(m) + '</small>' : '') + '</span>'; });
  int1 += '</div>';
  // cobertura: parte da área × parte da emissão (acumulado)
  let cv = '<div class="rk" style="grid-template-columns:minmax(120px,auto) 1fr 64px"><span class="h"></span><span class="h">% da área (vermelho) e % da emissão (roxo)</span><span class="h r">t CO₂e/ha</span>';
  const mx = Math.max(...GROUPS.map((_, g) => Math.max(pct(ra.gA[g], ra.A), pct(ra.gE[g], ra.E))), 1);
  GROUPS.forEach((n, g) => { if (!(ra.gA[g] > 0)) return; const a = pct(ra.gA[g], ra.A), e = pct(ra.gE[g], ra.E);
    cv += '<span class="nm"><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:' + gColor(g) + ';margin-right:5px"></i>' + esc(n) + '</span><span><span class="cell"><i style="width:' + (a / mx * 80) + '%;height:9px;background:var(--area)"></i><span>' + pctTxt(a) + '</span></span>'
      + '<span class="cell" style="margin-top:2px"><i style="width:' + (e / mx * 80) + '%;height:9px;background:var(--emis)"></i><span>' + pctTxt(e) + '</span></span></span><span class="r">' + nf(1).format(ra.gE[g] / ra.gA[g]) + '</span>'; });
  cv += '</div>';
  // texto guiado pelos dados: coberturas com maior e menor emissão por ha (entre as que têm ao menos 1% da área)
  const gi = GROUPS.map((_, g) => g).filter(g => pct(ra.gA[g], ra.A) >= 1).sort((a, b) => ra.gE[b] / ra.gA[b] - ra.gE[a] / ra.gA[a]);
  const bi = rowsI.filter(b => r.bA[b] >= 1000);
  let lead6 = 'A área queimada mostra onde e quanto queimou; a emissão mostra o peso de cada fogo para o clima, porque cada hectare queimado libera uma quantidade diferente de carbono.';
  if (bi.length > 1) lead6 += ' Em ' + MES[mo - 1] + ', um hectare queimado ' + emB(BIOMES[bi[0]]) + BIOMES[bi[0]] + ' emitiu ' + nf(1).format(r.bE[bi[0]] / r.bA[bi[0]]) + ' t CO₂e, contra '
    + nf(1).format(r.bE[bi[bi.length - 1]] / r.bA[bi[bi.length - 1]]) + ' ' + emB(BIOMES[bi[bi.length - 1]]) + BIOMES[bi[bi.length - 1]] + '.';
  if (gi.length > 1) lead6 += ' No acumulado do ano, ' + GROUPS[gi[0]] + ' emitiu ' + nf(1).format(ra.gE[gi[0]] / ra.gA[gi[0]]) + ' t CO₂e por hectare queimado e '
    + GROUPS[gi[gi.length - 1]] + ', ' + nf(1).format(ra.gE[gi[gi.length - 1]] / ra.gA[gi[gi.length - 1]]) + '.';
  const gt = r.gas[0] + r.gas[1] + r.gas[2], gc = ['#9a3f12', '#008ba3', '#6a4fc9'], gn = ['CO₂', 'CH₄', 'N₂O'];
  const gas = '<div class="gasbar">' + r.gas.map((v, i) => '<span style="flex:' + v + ';background:' + gc[i] + '">' + (pct(v, gt) >= 9 ? gn[i] + ' ' + pctTxt(pct(v, gt)) : '') + '</span>').join('') + '</div>'
    + '<div class="leg">' + r.gas.map((v, i) => '<span><i style="background:' + gc[i] + '"></i>' + gn[i] + ': ' + words(v, 't CO₂e') + ' (' + pctTxt(pct(v, gt)) + ')</span>').join('') + '</div>';
  return '<section class="pg" id="p6">' + pageHead(ctx) + '<div class="kick">Área × emissão</div><h1>O que a emissão acrescenta à área queimada</h1>'
    + '<p class="lead">' + esc(lead6) + '</p>'
    + '<div class="ck"><div><h3>Emissão por hectare queimado, por bioma</h3><p class="sub">' + cap(MES[mo - 1]) + ' de ' + y + ', em t CO₂e/ha · traço: média do mesmo mês em ' + years[0] + '–' + (y - 1) + '</p>' + int1
    + '<h3>Gases emitidos</h3><p class="sub">' + cap(MES[mo - 1]) + ' de ' + y + ', em CO₂ equivalente</p>' + gas
    + '<h3>Mesma área no Monitor do Fogo</h3><p class="sub">Área queimada no Brasil e nos biomas em ' + MES[mo - 1] + ' de ' + y + ': na plataforma do Monitor do Fogo e na base de cálculo da emissão</p><div id="apiBox" class="note">Consultando a plataforma…</div></div>'
    + '<div><h3>Parte da área e parte da emissão, por cobertura</h3><p class="sub">Jan–' + MES3[mo - 1] + ' de ' + y + ' · quando a barra roxa passa da vermelha, a cobertura emite mais do que a sua parte na área</p>' + cv + '</div></div>'
    + foot(ctx, 6, 'Plataforma: plataforma.monitorfogo.mapbiomas.org.') + '</section>';
}

// consulta a área do mês na API pública do Monitor do Fogo (se estiver acessível)
const API = 'https://plataforma.monitorfogo.mapbiomas.org/api/statistics/area/';
const BIOME_CD = { 'Amazônia': 1, 'Caatinga': 2, 'Cerrado': 3, 'Mata Atlântica': 4, 'Pampa': 5, 'Pantanal': 6 };
let apiSeq = 0;
async function fillApi(ctx) {
  const seq = ++apiSeq, box = $('apiBox'), { y, mo } = ctx, r = sum(months(y, mo, false));
  const q = '?year=' + y + '&monthStart=' + mo + '&monthEnd=' + mo;
  const items = [['Brasil', API + 'country/0/state' + q, r.A], ...BIOMES.map((b, k) => [b, API + 'biome/' + BIOME_CD[b] + '/biome' + q, r.bA[k]])];
  try {
    const got = await Promise.all(items.map(([, url]) => fetch(url).then(x => x.ok ? x.json() : null).catch(() => null)));
    if (seq !== apiSeq) return;
    if (got.every(g => !g || g.areaHa == null)) throw new Error('vazio');
    let t = '<table class="cmp"><thead><tr><th>Território</th><th>Monitor do Fogo (ha)</th><th>Com emissão estimada (ha)</th><th>Cobertura</th></tr></thead><tbody>';
    items.forEach(([n, , ours], i) => { const a = got[i] && got[i].areaHa; if (a == null) return;
      t += '<tr><td>' + esc(n) + '</td><td>' + int(a) + '</td><td>' + int(ours) + '</td><td>' + (a > 0 ? nf(1).format(ours / a * 100) + '%' : '—') + '</td></tr>'; });
    box.innerHTML = t + '</tbody></table><p class="note">A diferença são áreas sem vegetação para queimar (água, áreas urbanas e outras áreas não vegetadas), que ficam fora da estimativa de emissão.</p>';
  } catch (e) {
    if (seq === apiSeq) box.textContent = 'Não foi possível consultar a plataforma do Monitor do Fogo agora. Nos meses já comparados, a área com emissão estimada fica acima de 95% da área da plataforma.';
  }
}

function render(mi) {
  const ym = MONTHS[mi], y = +ym.slice(0, 4), mo = +ym.slice(5), last = MONTHS[NM - 1];
  const y0 = +MONTHS[0].slice(0, 4), years = []; for (let yy = y0; yy <= y; yy++) if (mIdx(yy, mo) >= 0) years.push(yy);
  const ctx = { y, mo, years, lastY: +last.slice(0, 4), lastMo: +last.slice(5) };
  document.title = 'Destaques de ' + MES[mo - 1] + ' de ' + y;
  $('main').innerHTML = page1(ctx) + mapPage(ctx, 'b') + detailPage(ctx, 'b') + mapPage(ctx, 'u') + detailPage(ctx, 'u') + page6(ctx);
  document.querySelectorAll('.tog').forEach(tg => tg.addEventListener('click', ev => {
    const bt = ev.target.closest('button'); if (!bt) return; const wrap = tg.closest('.mapwrap');
    tg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === bt)));
    wrap.querySelectorAll('[data-map]').forEach(el => { el.hidden = el.dataset.map !== bt.dataset.k; });
  }));
  fillApi(ctx);
}

// mês: ?m=AAAA-MM ou o último disponível
const sel = $('selM');
MONTHS.map((m, i) => [m, i]).reverse().forEach(([m, i]) => { const o = document.createElement('option'); o.value = m; o.textContent = cap(MES[+m.slice(5) - 1]) + ' de ' + m.slice(0, 4); sel.appendChild(o); });
const want = new URLSearchParams(location.search).get('m');
const start = MONTHS.includes(want) ? want : MONTHS[NM - 1];
sel.value = start; render(MONTHS.indexOf(start));
sel.addEventListener('change', () => { const u = new URL(location.href); u.searchParams.set('m', sel.value); history.replaceState(null, '', u); render(MONTHS.indexOf(sel.value)); });
$('btnPrint').addEventListener('click', () => window.print());
// impressão sempre no tema claro
let themeBeforePrint = null;
window.addEventListener('beforeprint', () => { themeBeforePrint = document.documentElement.getAttribute('data-theme'); document.documentElement.setAttribute('data-theme', 'light'); });
window.addEventListener('afterprint', () => { if (themeBeforePrint) document.documentElement.setAttribute('data-theme', themeBeforePrint); });
</script>
__SITE_JS__
</body>
</html>
"""
