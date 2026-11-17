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
            "method": method_payload(), "unc": unc_payload(class_list),
            "dm_year": {str(int(k)): round(float(v), 1) for k, v in monitor_dry_matter(df).items()}}


# ---------------- incerteza ----------------
# Desvio-padrão relativo de cada componente (tratado como desvio em log). A emissão é um produto
# (área × estoque × combustão ÷ 0,47 × fator de emissão × GWP), então os desvios se combinam em
# quadratura dentro de cada classe e gás. Entre linhas, os limites são somados (erros sistemáticos,
# totalmente correlacionados), o que dá uma faixa conservadora.
UNC_Z = 1.96
UNC_AREA = (0.10, "premissa", "Área queimada (MapBiomas Fogo)")
UNC_FC = (0.03, "IPCC 2006: 0,47 (0,44 a 0,49)", "Fração de carbono da matéria seca")
UNC_STOCK = {"nativa": (0.30, "premissa", "Estoque de carbono, mapa (formações nativas)"),
             "agro": (0.40, "premissa", "Estoque médio do bioma (pastagem e agricultura)")}
UNC_CF = (0.20, "premissa", "Fator de combustão")
_EF_SAV = {"CO2": 95 / 1613, "CH4": 0.9 / 2.3, "N2O": 0.10 / 0.21}
UNC_EF = {  # IPCC 2006, vol. 4, tab. 2.5 (média ± DP); onde a tabela não traz DP, premissa de 50%
    "Formação Florestal": {"CO2": 90 / 1580, "CH4": 2.0 / 6.8, "N2O": 0.5},
    "Formação Savânica": _EF_SAV, "Formação Campestre": _EF_SAV,
    "Campo Alagado e Área Pantanosa": _EF_SAV, "Pastagem": _EF_SAV,
    "Agricultura": {"CO2": 177 / 1515, "CH4": 0.5, "N2O": 0.5},
}
UNC_EF_SRC = "IPCC 2006, vol. 4, tab. 2.5 (DP publicado); 50% onde não há DP"


def _class_category():
    out = {}
    for cat, codes in _pe.CLASSES.items():
        for c in codes:
            out[c] = cat
    return out


def unc_sigma(cat, gas):
    stock = UNC_STOCK["agro" if cat in _pe.ANTROPICAS else "nativa"][0]
    ef = UNC_EF.get(cat, _EF_SAV)[gas]
    return (UNC_AREA[0] ** 2 + UNC_FC[0] ** 2 + stock ** 2 + UNC_CF[0] ** 2 + ef ** 2) ** 0.5


def unc_payload(class_list):
    cc = _class_category()
    sig = [[round(unc_sigma(cc.get(c["id"], "Formação Savânica"), g), 4) for g in ("CO2", "CH4", "N2O")]
           for c in class_list]
    pct = lambda v: f"{_fmt(v * 100)}%"
    rows = [[UNC_AREA[2], pct(UNC_AREA[0]), UNC_AREA[1]],
            [UNC_STOCK["nativa"][2], pct(UNC_STOCK["nativa"][0]), UNC_STOCK["nativa"][1]],
            [UNC_STOCK["agro"][2], pct(UNC_STOCK["agro"][0]), UNC_STOCK["agro"][1]],
            [UNC_CF[2], pct(UNC_CF[0]), UNC_CF[1]],
            [UNC_FC[2], pct(UNC_FC[0]), UNC_FC[1]],
            ["Fator de emissão de CO₂", f"{pct(min(v['CO2'] for v in UNC_EF.values()))} a {pct(max(v['CO2'] for v in UNC_EF.values()))}", UNC_EF_SRC],
            ["Fator de emissão de CH₄", f"{pct(min(v['CH4'] for v in UNC_EF.values()))} a {pct(max(v['CH4'] for v in UNC_EF.values()))}", UNC_EF_SRC],
            ["Fator de emissão de N₂O", f"{pct(min(v['N2O'] for v in UNC_EF.values()))} a {pct(max(v['N2O'] for v in UNC_EF.values()))}", UNC_EF_SRC]]
    return {"z": UNC_Z, "sig": sig, "rows": rows}


# ---------------- comparação externa ----------------
EXTERNAL_DEFAULT = HERE / ("../data/externo/comparacao_anual.csv" if HERE.name == "src" else "externo/comparacao_anual.csv")


def external_payload(path):
    """CSV longo: fonte, ano, variavel (CO2|CH4|N2O|MS), valor_t, escopo. Ausente: sem comparação."""
    path = Path(path)
    if not path.exists():
        return None
    ext = pd.read_csv(path)
    need = {"fonte", "ano", "variavel", "valor_t"}
    if need - set(ext.columns):
        raise SystemExit(f"{path}: colunas ausentes {sorted(need - set(ext.columns))}")
    rows = [[str(r.fonte), int(r.ano), str(r.variavel), float(r.valor_t)] for r in ext.itertuples()]
    notes = {}
    if "escopo" in ext.columns:
        for f, g in ext.groupby("fonte"):
            notes[str(f)] = str(g["escopo"].dropna().iloc[0]) if g["escopo"].notna().any() else ""
    return {"rows": rows, "notes": notes}


def monitor_dry_matter(df):
    """Matéria seca queimada (t) por ano, recuperada do CO₂: MS = CO₂ ÷ (EF_CO₂/1000)."""
    cc = _class_category()
    ef = df["class_int"].map(lambda c: _pe.FATORES_POR_GAS["CO2"].get(cc.get(int(c), "Formação Savânica")))
    ms = df[GAS_COLS["co2"]] / (ef / 1000.0)
    return ms.groupby(df["Ano"]).sum()


# ---------------- diagramas da página de método (SVG inline) ----------------
def _fmt(v, d=0):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tx(x, y, text, cls="s-t", anchor="middle"):
    return f'<text x="{x:g}" y="{y:g}" class="{cls}" text-anchor="{anchor}">{text}</text>'


def _marker(mid, cls="s-arw"):
    return (f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="{cls}"/></marker></defs>')


def _svg(w, h, label, body, wide=True, caption=""):
    cls = "dg wide" if wide else "dg"
    return (f'<figure class="{cls}"><div class="sc"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{label}">'
            f'{body}</svg></div><figcaption>{caption}</figcaption></figure>')


def _cover_color(name):
    return dict(COVER).get(name, COVER_OTHER[1])


def svg_overview():
    m = "ar-ov"
    b = [_marker(m)]
    x0, w, gap, y, h = 196, 132, 22, 112, 84
    cy = y + h / 2
    inputs = [("Fogo do mês", "onde e quando queimou", 74), ("Cobertura do ano", "o que queimou", 130),
              ("Biomas e estados", "parâmetros e recortes", 186)]
    for t, sub, iy in inputs:
        b.append(f'<rect x="8" y="{iy}" width="150" height="48" rx="9" class="s-in"/>')
        b.append(_tx(83, iy + 21, t)); b.append(_tx(83, iy + 38, sub, "s-tm"))
        my = iy + 24
        b.append(f'<path d="M158,{my} C178,{my} 176,{cy} {x0 - 2},{cy}" class="s-ln" marker-end="url(#{m})"/>')
    steps = [("Pixel queimado", "fogo + cobertura", "classe e bioma", "6 categorias de vegetação"),
             ("Carbono queimado", "estoque × combustão", "t C/ha", "fator por bioma e classe"),
             ("Biomassa queimada", "÷ 0,47", "t matéria seca/ha", "47% da matéria seca é carbono"),
             ("Gases emitidos", "× fator de emissão", "CO₂ · CH₄ · N₂O", "g por kg de matéria seca"),
             ("CO₂ equivalente", "× GWP (IPCC AR5)", "t CO₂e/ha", "CH₄ 28 · N₂O 265"),
             ("Toneladas", "× área do pixel, Σ", "bioma × UF × classe", "≈ 0,09 ha por pixel")]
    for i, (t, op, unit, tag) in enumerate(steps):
        x = x0 + i * (w + gap)
        last = i == len(steps) - 1
        b.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="{"s-out" if last else "s-box"}"/>')
        b.append(_tx(x + w / 2, y + 26, t, "s-t s-on" if last else "s-t"))
        b.append(_tx(x + w / 2, y + 48, op, "s-op s-on" if last else "s-op"))
        b.append(_tx(x + w / 2, y + 68, unit, "s-tm s-on" if last else "s-tm"))
        b.append(_tx(x + w / 2, y + h + 22, tag, "s-tm"))
        if not last:
            b.append(f'<line x1="{x + w}" y1="{cy}" x2="{x + w + gap - 2}" y2="{cy}" class="s-ln" marker-end="url(#{m})"/>')
    cx = x0 + (w + gap) + w / 2
    b.append(f'<rect x="{cx - 75}" y="10" width="150" height="48" rx="9" class="s-in"/>')
    b.append(_tx(cx, 31, "Estoque de carbono")); b.append(_tx(cx, 48, "mapa de 2019 · médias", "s-tm"))
    b.append(f'<line x1="{cx}" y1="58" x2="{cx}" y2="{y - 2}" class="s-ln" marker-end="url(#{m})"/>')
    end = x0 + 6 * w + 5 * gap
    b.append(f'<path d="M{x0},244 v8 H{end} v-8" class="s-lnd"/>')
    b.append(_tx((x0 + end) / 2, 274, "repetido para cada mês desde janeiro de 2019, em todos os pixels de 30 m do país", "s-t2"))
    return _svg(1110, 290, "Visão geral: fogo, cobertura e limites identificam o pixel queimado; o carbono queimado é convertido "
                "em biomassa, gases, CO2 equivalente e somado em toneladas por bioma, UF e classe.", "".join(b),
                caption="Toda a estimativa em uma linha: cada caixa é uma etapa, e o texto em destaque é a operação aplicada "
                        "sobre o resultado da etapa anterior.")


def svg_layers():
    m = "ar-ly"
    b = [_marker(m, "s-arw-a")]
    F, S, P, C, A = (_cover_color(n) for n in ["Formação Florestal", "Formação Savânica", "Pastagem",
                                                 "Formação Campestre", "Agricultura"])
    cover = ["FFFSSP", "FFSSSP", "FSSSCP", "SSSCCA", "SPPCAA", "PPPAAA"]
    cmap = {"F": F, "S": S, "P": P, "C": C, "A": A}
    burned = {(1, 1), (2, 1), (2, 2), (3, 2), (3, 3), (2, 3), (4, 3), (4, 4)}
    hl = (3, 2)
    cs, sh, sv = 24, 0.85, 0.42
    tx = 150
    layers = [("Fogo do mês", "MapBiomas Fogo", 20), ("Cobertura do ano", "MapBiomas", 120), ("Bioma e estado", "IBGE", 220)]
    for li, (t, sub, ty) in enumerate(layers):
        b.append(_tx(8, ty + 26, t, "s-t", "start")); b.append(_tx(8, ty + 43, sub, "s-tm", "start"))
        g = [f'<g transform="translate({tx},{ty}) matrix(1 0 {sh} {sv} 0 0)">']
        for r in range(6):
            for c in range(6):
                if li == 0:
                    cls = "s-burn" if (c, r) in burned else "s-cell"
                    g.append(f'<rect x="{c * cs}" y="{r * cs}" width="{cs}" height="{cs}" class="{cls} s-seam"/>')
                elif li == 1:
                    g.append(f'<rect x="{c * cs}" y="{r * cs}" width="{cs}" height="{cs}" fill="{cmap[cover[r][c]]}" class="s-seam"/>')
                else:
                    cls = "s-bio1" if c < 4 else "s-bio2"
                    g.append(f'<rect x="{c * cs}" y="{r * cs}" width="{cs}" height="{cs}" class="{cls} s-seam"/>')
        if li == 2:
            g.append(f'<line x1="0" y1="{4 * cs}" x2="{4 * cs}" y2="{4 * cs}" class="s-uf"/>')
            g.append(f'<line x1="{4 * cs}" y1="0" x2="{4 * cs}" y2="{6 * cs}" class="s-bline"/>')
        g.append(f'<rect x="{hl[0] * cs}" y="{hl[1] * cs}" width="{cs}" height="{cs}" class="s-hl"/>')
        g.append('</g>')
        b.append("".join(g))
    px = tx + (hl[0] + 0.5) * cs + sh * (hl[1] + 0.5) * cs
    off = sv * (hl[1] + 0.5) * cs
    b.append(f'<line x1="{px:.1f}" y1="{20 + off:.1f}" x2="{px:.1f}" y2="{220 + off:.1f}" class="s-acc-d"/>')
    cardx, cardw = 480, 230
    b.append(f'<rect x="{cardx}" y="14" width="{cardw}" height="262" rx="12" class="s-box"/>')
    rows = [("fogo do mês", "queimou em agosto", 20), ("cobertura do ano", "Formação Savânica", 120),
            ("bioma e estado", "Cerrado · Goiás", 220)]
    for k, v, ty in rows:
        yy = ty + off
        b.append(f'<circle cx="{px:.1f}" cy="{yy:.1f}" r="3.5" class="s-dot"/>')
        b.append(f'<line x1="{px:.1f}" y1="{yy:.1f}" x2="{cardx - 2}" y2="{yy:.1f}" class="s-acc-ln" marker-end="url(#{m})"/>')
        b.append(_tx(cardx + 18, yy - 8, k, "s-tm", "start")); b.append(_tx(cardx + 18, yy + 10, v, "s-t", "start"))
    b.append(f'<line x1="{cardx + cardw}" y1="145" x2="{cardx + cardw + 30}" y2="145" class="s-ln" marker-end="url(#ar-ly2)"/>')
    b.append(_marker("ar-ly2"))
    rx = cardx + cardw + 34
    b.append(f'<rect x="{rx}" y="96" width="176" height="98" rx="12" class="s-out"/>')
    b.append(_tx(rx + 88, 124, "Savânica do Cerrado", "s-t s-on"))
    b.append(_tx(rx + 88, 146, "define a combustão,", "s-tm s-on"))
    b.append(_tx(rx + 88, 162, "os compartimentos e os", "s-tm s-on"))
    b.append(_tx(rx + 88, 178, "fatores de emissão", "s-tm s-on"))
    return _svg(930, 290, "As camadas de fogo do mês, cobertura do ano e bioma/estado são cruzadas pixel a pixel; "
                "o pixel em destaque queimou em agosto, é formação savânica e está no Cerrado, em Goiás.", "".join(b),
                caption="Três mapas sobrepostos: para cada pixel queimado no mês (em destaque), a cobertura daquele ano e o bioma "
                        "definem quais parâmetros de queima se aplicam; o estado define onde a emissão é somada.")


def svg_pools():
    cats = ["Formação Florestal", "Formação Savânica", "Formação Campestre", "Campo Alagado e Área Pantanosa",
            "Pastagem", "Agricultura"]
    short = {"Campo Alagado e Área Pantanosa": "Campo alagado"}
    first = next(iter(_pe.FATORES_POR_BIOMA.values()))
    pools = [("AGB", "biomassa aérea", 40, 92), ("DW", "madeira morta", 138, 32), ("LI", "serrapilheira", 176, 24)]
    x0, w, gap = 150, 118, 24
    b = []
    for k, name, y, h in pools:
        b.append(_tx(x0 - 14, y + h / 2 + 4, name, "s-t2", "end"))
    nat_end = x0 + 4 * (w + gap) - gap
    b.append(f'<path d="M{x0},26 v-6 H{nat_end} v6" class="s-lnd"/>')
    b.append(_tx((x0 + nat_end) / 2, 14, "formações nativas: mapa de carbono, pixel a pixel", "s-tm"))
    ag0 = x0 + 4 * (w + gap)
    ag_end = ag0 + 2 * (w + gap) - gap
    b.append(f'<path d="M{ag0},26 v-6 H{ag_end} v6" class="s-lnd"/>')
    b.append(_tx((ag0 + ag_end) / 2, 14, "agropecuária: média do bioma", "s-tm"))
    for i, cat in enumerate(cats):
        x = x0 + i * (w + gap)
        col = _cover_color(cat)
        coef = _pool_coefs(first[cat]["c_pool"])
        if cat in _pe.ANTROPICAS:
            b.append(f'<rect x="{x}" y="40" width="{w}" height="160" rx="6" fill="{col}" class="s-seam"/>')
            b.append(_tx(x + w / 2, 116, "estoque médio", "s-t2 s-dark"))
            b.append(_tx(x + w / 2, 132, "do bioma", "s-t2 s-dark"))
        else:
            for k, name, y, h in pools:
                c = coef[k]
                if c <= 0:
                    b.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="s-no"/>')
                    b.append(_tx(x + w / 2, y + h / 2 + 4, "não entra", "s-tm"))
                elif c >= 1:
                    b.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{col}" class="s-seam"/>')
                else:
                    fh = h * c
                    b.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="s-no"/>')
                    b.append(f'<rect x="{x}" y="{y + h - fh:.1f}" width="{w}" height="{fh:.1f}" rx="5" fill="{col}" class="s-seam"/>')
                    b.append(_tx(x + w / 2, y + (h - fh) / 2 + 4, f"{_fmt(c * 100)}% entra", "s-t2"))
        cfs = [v[cat]["cf"] for v in _pe.FATORES_POR_BIOMA.values()]
        lo, hi = min(cfs), max(cfs)
        rng = _fmt(lo, 2) if abs(hi - lo) < 1e-9 else f"{_fmt(lo, 2)}–{_fmt(hi, 2)}"
        b.append(_tx(x + w / 2, 222, short.get(cat, cat.replace("Formação ", "")), "s-t"))
        b.append(_tx(x + w / 2, 240, f"combustão {rng}", "s-op s-sm"))
    return _svg(1000, 254, "Compartimentos de carbono por categoria: floresta usa madeira morta e serrapilheira; savana usa 26% "
                "da biomassa aérea mais os resíduos; campos usam todos; pastagem e agricultura usam o estoque médio do bioma.",
                "".join(b),
                caption="O que pode queimar em cada tipo de vegetação. Áreas coloridas entram no cálculo; tracejadas não. "
                        "Abaixo, o fator de combustão (a fração consumida pelo fogo), que varia por bioma. Alturas ilustrativas.")


def svg_mass(cat="Formação Savânica"):
    ef = {g: _pe.FATORES_POR_GAS[g][cat] for g in ("CO2", "CH4", "N2O")}
    gwp = {"CO2": 1, **_pe.GWP_AR5}
    ms = 1 / _pe.CARBON_FRACTION
    mass_t = {g: ms * ef[g] / 1000 for g in ef}
    co2e = {g: mass_t[g] * gwp[g] for g in ef}
    tot = sum(co2e.values())
    m = "ar-ms"
    b = [_marker(m)]
    b.append(f'<rect x="10" y="95" width="130" height="64" rx="10" class="s-in"/>')
    b.append(_tx(75, 122, "1 t de carbono")); b.append(_tx(75, 141, "queimado", "s-tm"))
    b.append(f'<line x1="140" y1="127" x2="196" y2="127" class="s-ln" marker-end="url(#{m})"/>')
    b.append(_tx(168, 118, "÷ 0,47", "s-op"))
    b.append(f'<rect x="200" y="95" width="140" height="64" rx="10" class="s-box"/>')
    b.append(_tx(270, 122, f"{_fmt(ms, 2)} t")); b.append(_tx(270, 141, "de matéria seca", "s-tm"))
    names = {"CO2": "CO₂", "CH4": "CH₄", "N2O": "N₂O"}
    ys = {"CO2": 30, "CH4": 95, "N2O": 160}
    scale = 300 / tot
    for g in ("CO2", "CH4", "N2O"):
        y = ys[g]
        cy = y + 32
        b.append(f'<path d="M340,127 C370,127 370,{cy} {418},{cy}" class="s-ln" marker-end="url(#{m})"/>')
        b.append(f'<rect x="420" y="{y}" width="150" height="64" rx="10" class="s-box"/>')
        massv = f"{_fmt(mass_t[g], 2)} t" if mass_t[g] >= 1 else f"{_fmt(mass_t[g] * 1000, 1 if mass_t[g] >= 0.001 else 2)} kg"
        b.append(_tx(495, y + 26, f"{massv} de {names[g]}"))
        b.append(_tx(495, y + 45, f"{_fmt(ef[g], 0 if ef[g] >= 100 else (1 if ef[g] >= 1 else 2))} g por kg", "s-tm"))
        b.append(f'<line x1="570" y1="{cy}" x2="636" y2="{cy}" class="s-ln" marker-end="url(#{m})"/>')
        b.append(_tx(603, cy - 7, f"× {gwp[g]}", "s-op"))
        bw = max(co2e[g] * scale, 3)
        b.append(f'<rect x="640" y="{cy - 11}" width="{bw:.1f}" height="22" rx="4" class="s-burn"/>')
        b.append(_tx(640 + bw + 8, cy + 4, f"{_fmt(co2e[g], 2)} t CO₂e", "s-t2", "start"))
    b.append(f'<line x1="640" y1="226" x2="{640 + tot * scale:.1f}" y2="226" class="s-acc-ln"/>')
    b.append(_tx(640, 248, f"= {_fmt(tot, 2)} t CO₂e", "s-t", "start"))
    return _svg(1000, 262, f"De 1 tonelada de carbono queimado em {cat.lower()}: {_fmt(ms, 2)} t de matéria seca, que emitem CO2, "
                f"CH4 e N2O; convertidos pelo GWP, somam {_fmt(tot, 2)} t de CO2 equivalente.", "".join(b),
                caption=f"O caminho de 1 tonelada de carbono queimado ({cat.lower()}). CH₄ e N₂O saem em quilos, "
                        f"mas o GWP multiplica seu efeito: juntos, respondem por "
                        f"{_fmt((co2e['CH4'] + co2e['N2O']) / tot * 100, 0)}% do CO₂e.")


def svg_aggregate():
    m = "ar-ag"
    b = [_marker(m)]
    S, P, F = (_cover_color(n) for n in ["Formação Savânica", "Pastagem", "Formação Florestal"])
    cs, gx, gy = 22, 30, 36
    burn = {(1, 1): S, (2, 1): S, (2, 2): S, (3, 2): S, (1, 3): P, (2, 4): P, (3, 4): P, (5, 1): F,
            (6, 1): F, (6, 2): S, (5, 5): P, (6, 5): P, (6, 6): P, (2, 6): S}
    for r in range(8):
        for c in range(8):
            fill = burn.get((c, r))
            if fill:
                b.append(f'<rect x="{gx + c * cs}" y="{gy + r * cs}" width="{cs}" height="{cs}" fill="{fill}" class="s-seam"/>')
            else:
                b.append(f'<rect x="{gx + c * cs}" y="{gy + r * cs}" width="{cs}" height="{cs}" class="s-cell s-seam"/>')
    b.append(f'<line x1="{gx + 5 * cs}" y1="{gy - 6}" x2="{gx + 5 * cs}" y2="{gy + 8 * cs + 6}" class="s-uf"/>')
    b.append(_tx(gx + 2.5 * cs, gy - 12, "Goiás", "s-t2")); b.append(_tx(gx + 6.5 * cs, gy - 12, "Minas Gerais", "s-t2"))
    b.append(_tx(gx + 4 * cs, gy + 8 * cs + 26, "pixels queimados no mês (Cerrado)", "s-tm"))
    b.append(f'<line x1="{gx + 8 * cs + 4}" y1="124" x2="246" y2="124" class="s-ln" marker-end="url(#{m})"/>')
    b.append(f'<rect x="250" y="82" width="170" height="84" rx="10" class="s-box"/>')
    b.append(_tx(335, 108, "cada pixel")); b.append(_tx(335, 128, "t CO₂e/ha × área", "s-op"))
    b.append(_tx(335, 147, "≈ 0,09 ha", "s-tm"))
    b.append(f'<line x1="420" y1="124" x2="486" y2="124" class="s-ln" marker-end="url(#{m})"/>')
    b.append(_tx(453, 116, "Σ", "s-op"))
    tx0, tw = 490, 400
    b.append(f'<rect x="{tx0}" y="30" width="{tw}" height="190" rx="10" class="s-box"/>')
    b.append(_tx(tx0 + 16, 54, "bioma · estado · classe · mês", "s-tm", "start"))
    b.append(_tx(tx0 + tw - 16, 54, "t CO₂e", "s-tm", "end"))
    b.append(f'<line x1="{tx0 + 12}" y1="62" x2="{tx0 + tw - 12}" y2="62" class="s-rule"/>')
    def n(col, mg):
        k = sum(1 for (c, _), v in burn.items() if v == col and (c >= 5) == mg)
        return f"Σ de {k} pixel" + ("s" if k > 1 else "")
    rows = [(S, "Cerrado · GO · Savânica · ago", n(S, False)), (P, "Cerrado · GO · Pastagem · ago", n(P, False)),
            (F, "Cerrado · MG · Florestal · ago", n(F, True)), (S, "Cerrado · MG · Savânica · ago", n(S, True)),
            (P, "Cerrado · MG · Pastagem · ago", n(P, True))]
    for i, (col, lab, v) in enumerate(rows):
        yy = 86 + i * 28
        b.append(f'<rect x="{tx0 + 16}" y="{yy - 10}" width="12" height="12" rx="3" fill="{col}" class="s-seam"/>')
        b.append(_tx(tx0 + 36, yy, lab, "s-t2", "start")); b.append(_tx(tx0 + tw - 16, yy, v, "s-t2", "end"))
    return _svg(900, 252, "Cada pixel queimado tem sua emissão por hectare multiplicada pela área do pixel e somada por bioma, "
                "estado, classe e mês, formando a tabela de estatísticas.", "".join(b),
                caption="Do mapa à tabela: a emissão de cada pixel vira toneladas pela sua área real e é somada em cada "
                        "combinação de bioma, estado, classe e mês. Essa tabela alimenta todos os gráficos do painel.")


def svg_density():
    b = []
    dots = [(0.2, 0.3), (0.35, 0.6), (0.6, 0.25), (0.7, 0.7), (0.45, 0.45), (0.8, 0.4), (0.25, 0.8), (0.55, 0.85)]

    def terr(x, y, size, name, area, dens):
        out = [f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="6" class="s-terr"/>']  # território
        for fx, fy in dots:
            out.append(f'<rect x="{x + fx * size - 4:.1f}" y="{y + fy * size - 4:.1f}" width="8" height="8" rx="1.5" class="s-burn"/>')
        tx = x + size + 18
        out.append(_tx(tx, y + 18, name, "s-t", "start"))
        out.append(_tx(tx, y + 38, "emissão: 2 milhões t CO₂e", "s-t2", "start"))
        out.append(_tx(tx, y + 55, "área queimada: 80 mil ha", "s-t2", "start"))
        out.append(_tx(tx, y + 72, f"território: {area} ha", "s-t2", "start"))
        out.append(_tx(tx, y + 96, "Σ emissão ÷ Σ área queimada = 25 t/ha", "s-t", "start"))
        out.append(_tx(tx, y + 116, f"Σ emissão ÷ Σ território = {dens} t/ha", "s-op s-big", "start"))
        return "".join(out)

    b.append(terr(20, 16, 160, "Recorte grande", "4 milhões de", "0,5"))
    b.append(terr(470, 56, 80, "Recorte pequeno", "1 milhão de", "2"))
    return _svg(880, 200, "Dois recortes com a mesma emissão e a mesma área queimada: os dois emitem 25 t por hectare queimado; "
                "por hectare de território, o grande tem 0,5 t e o pequeno, 2 t.", "".join(b), wide=False,
                caption="Mesma queima, territórios diferentes. A emissão por hectare queimado é igual (25 t/ha): o que queimou é parecido. "
                        "A emissão por hectare de território é quatro vezes maior no recorte quatro vezes menor: ali o fogo pesa mais na região.")


def svg_process():
    m = "ar-pr"
    b = [_marker(m)]
    zones = [(10, 390, "Google Earth Engine"), (410, 590, "Google Drive"), (610, 990, "Publicação")]
    for x1, x2, name in zones:
        b.append(f'<rect x="{x1}" y="16" width="{x2 - x1}" height="150" rx="12" class="s-zone"/>')
        b.append(_tx(x1 + 14, 38, name, "s-tm s-caps", "start"))
    boxes = [(30, "Mapas de emissão", "um por mês · 3 gases"), (230, "Estatísticas", "bioma × estado × classe"),
             (430, "Tabelas mensais", "uma por mês"), (630, "Base consolidada", "série completa, aberta"),
             (840, "Painel", "gráficos e matrizes")]
    labels = ["soma", "exporta", "reúne", "publica"]
    for i, (x, t, sub) in enumerate(boxes):
        last = i == len(boxes) - 1
        b.append(f'<rect x="{x}" y="70" width="140" height="66" rx="10" class="{"s-out" if last else "s-box"}"/>')
        b.append(_tx(x + 70, 98, t, "s-t s-on" if last else "s-t"))
        b.append(_tx(x + 70, 117, sub, "s-tm s-on" if last else "s-tm"))
        if not last:
            nx = boxes[i + 1][0]
            b.append(f'<line x1="{x + 140}" y1="103" x2="{nx - 2}" y2="103" class="s-ln" marker-end="url(#{m})"/>')
            b.append(_tx((x + 140 + nx) / 2, 95, labels[i], "s-op"))
    b.append(f'<path d="M910,136 V188 H100 V{140}" class="s-lnd" marker-end="url(#{m})"/>')
    b.append(_tx(505, 182, "novo mês do MapBiomas Fogo: o ciclo se repete e a série é atualizada", "s-t2"))
    return _svg(1000, 200, "Processo: mapas de emissão mensais e estatísticas no Google Earth Engine, tabelas mensais no Google "
                "Drive, base consolidada e painel publicados; o ciclo se repete a cada novo mês.", "".join(b),
                caption="Do satélite ao painel. Todo o cálculo pesado roda na nuvem; cada novo mês de área queimada passa "
                        "pelas mesmas etapas, sem reprocessar a série.")


def method_svgs():
    return {"__SVG_OVERVIEW__": svg_overview(), "__SVG_LAYERS__": svg_layers(), "__SVG_POOLS__": svg_pools(),
            "__SVG_MASS__": svg_mass(), "__SVG_AGG__": svg_aggregate(), "__SVG_DENS__": svg_density(),
            "__SVG_PROCESS__": svg_process()}


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
  --g-co2: #9a3f12; --g-ch4: #008ba3; --g-n2o: #6a4fc9;
  --x1: #3f6f9e; --x2: #6b7f22;
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
  --g-co2: #e0703a; --g-ch4: #1aa3b8; --g-n2o: #8f78e6;
  --x1: #6f9fd0; --x2: #a3b54a;
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
#fMeasure { --cols: 2; } #fGas { --cols: 4; } #fCover { --cols: 3; }
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
.kpis { grid-template-columns: 1fr 1.5fr 1fr 1fr 1fr; margin-bottom: 16px; }
.unc { font-size: 12px; color: var(--muted); margin-top: 4px; }
.sch3 { font-size: 13px; margin: 14px 0 6px; color: var(--ink); }
.anom { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 12.5px; color: var(--ink-2); }
.anom i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; box-shadow: inset 0 0 0 1px var(--seam); }
.anom b { color: var(--ink); font-weight: 650; }
table.sctab td.rd-up { color: var(--up); font-weight: 650; }
table.sctab td.rd-down { color: var(--down); font-weight: 650; }
.scctl { display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 8px 0 6px; }
.scctl > div { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
table.sctab td { color: var(--ink); }
table.sctab tbody tr { cursor: pointer; }
table.sctab tbody tr:hover td, table.sctab tbody tr:hover th { background: var(--accent-weak); }
table.sctab tbody tr.dim th, table.sctab tbody tr.dim td { opacity: .45; }
table.sctab tbody tr.on th { text-decoration: underline; text-underline-offset: 3px; }
table.sctab th i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 7px; vertical-align: -1px;
  box-shadow: inset 0 0 0 1px var(--seam); }
table.sctab .kbar { display: inline-block; height: 8px; border-radius: 2px; background: var(--accent); vertical-align: 0; margin-right: 6px; }
.mhint { margin: 2px 0 0; font-size: 12px; line-height: 1.4; color: var(--muted); }
.mhint b.fx { display: block; color: var(--ink); font-weight: 650; font-size: 12.5px; margin: 2px 0 2px;
  font-variant-numeric: tabular-nums; }
.tile .label abbr { text-decoration: none; }
.unc b { color: var(--ink-2); font-weight: 600; }
.gasbars { display: grid; gap: 8px; margin: 6px 0 12px; }
.gasbar { display: grid; grid-template-columns: 62px 1fr; gap: 10px; align-items: center; font-size: 12.5px; color: var(--ink-2); }
.gasbar .t { display: flex; gap: 2px; height: 16px; }
.gasbar .t span { min-width: 2px; border-radius: 3px; }
table.gastab { width: 100%; border-collapse: collapse; font-size: 12.5px; }
table.gastab th, table.gastab td { padding: 5px 4px; text-align: right; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
table.gastab th:first-child, table.gastab td:first-child { text-align: left; }
table.gastab thead th { color: var(--muted); font-weight: 600; font-size: 11.5px; position: static; background: none; }
table.gastab i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 6px; }
.gasnote { font-size: 12px; color: var(--muted); margin: 8px 0 0; }
.row2 { grid-template-columns: 2fr 1fr; margin-bottom: 16px; }
.row3 { grid-template-columns: 1fr 1fr; margin-bottom: 16px; }
@media (max-width: 1250px) { .kpis { grid-template-columns: 1fr 1fr 1fr; } .kpis .hero { grid-column: span 3; } }
@media (max-width: 960px) { .kpis { grid-template-columns: 1fr 1fr; } .kpis .hero { grid-column: span 2; } .row2, .row3 { grid-template-columns: 1fr; } }
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
/* ---- diagramas ---- */
.dg { margin: 18px 0 8px; }
.dg .sc { overflow-x: auto; }
.dg svg { display: block; width: 100%; height: auto; font-family: inherit; }
.dg.wide svg { min-width: 760px; }
.dg figcaption { font-size: 12.5px; color: var(--muted); margin-top: 8px; max-width: 820px; }
.s-box { fill: var(--surface); stroke: var(--axis); stroke-width: 1; }
.s-in { fill: var(--accent-weak); }
.s-out { fill: var(--accent); }
.s-zone { fill: none; stroke: var(--axis); stroke-dasharray: 5 4; }
.s-ln { stroke: var(--muted); stroke-width: 1.5; fill: none; }
.s-lnd { stroke: var(--muted); stroke-width: 1.2; fill: none; stroke-dasharray: 4 3; }
.s-acc-ln { stroke: var(--accent); stroke-width: 2; fill: none; }
.s-acc-d { stroke: var(--accent); stroke-width: 2; stroke-dasharray: 3 3; }
.s-rule { stroke: var(--grid); stroke-width: 1; }
.s-arw { fill: var(--muted); } .s-arw-a { fill: var(--accent); } .s-dot { fill: var(--accent); }
.s-t { fill: var(--ink); font-size: 13px; font-weight: 650; }
.s-t2 { fill: var(--ink-2); font-size: 12px; }
.s-tm { fill: var(--muted); font-size: 11px; }
.s-op { fill: var(--accent); font-size: 12px; font-weight: 700; }
.s-big { font-size: 15px; } .s-sm { font-size: 11px; }
.s-caps { text-transform: uppercase; letter-spacing: .06em; font-weight: 650; }
.s-on { fill: var(--on-accent); }
.s-dark { fill: #2a2119; }
.s-seam { stroke: var(--seam); stroke-width: 0.6; }
.s-cell { fill: var(--surface); }
.s-burn { fill: var(--accent); }
.s-bio1 { fill: #e3d3b4; } .s-bio2 { fill: #c9d6b6; }
:root[data-theme="dark"] .s-bio1 { fill: #5c4a33; } :root[data-theme="dark"] .s-bio2 { fill: #3f5136; }
:root[data-theme="dark"] .s-dark { fill: #2a2119; }
.s-uf { stroke: var(--ink); stroke-width: 2; stroke-dasharray: 5 3; }
.s-bline { stroke: var(--ink-2); stroke-width: 1.5; }
.s-hl { fill: none; stroke: var(--ink); stroke-width: 2.5; }
.s-no { fill: none; stroke: var(--axis); stroke-width: 1.2; stroke-dasharray: 4 3; }
.s-terr { fill: var(--accent-weak); stroke: var(--axis); }
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
      <div class="fgroup"><span class="flabel" id="lMeasure">Medida</span><div class="seg" id="fMeasure" role="group" aria-labelledby="lMeasure"></div>
        <p class="mhint" id="fMeasureHint" aria-live="polite"></p></div>
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
    <div class="card tile"><div class="label">Área queimada</div><div class="value" id="kArea"></div><div class="note" id="kAreaNote"></div></div>
    <div class="card tile hero"><div class="label" id="kEmissLabel">Emissão</div><div class="value" id="kEmiss"></div><div class="note" id="kEmissNote"></div><div class="unc" id="kEmissUnc"></div></div>
    <div class="card tile"><div class="label" id="kIntLabel">Emissão por hectare queimado</div><div class="value" id="kInt"></div><div class="note" id="kIntNote"></div></div>
    <div class="card tile"><div class="label" id="kDensLabel">Emissão por hectare de território</div><div class="value" id="kDens"></div><div class="note" id="kDensNote"></div></div>
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
      <p class="sub">Em massa, quase tudo é CO₂; no efeito sobre o clima (CO₂e, GWP AR5), CH₄ e N₂O ganham peso</p>
      <div class="gasbars" id="gasBars"></div>
      <table class="gastab" id="gasTab"></table>
      <p class="gasnote" id="gasNote"></p>
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
    <div class="card-head">
      <div><h2 id="tScatter">Área queimada × emissão</h2><p class="sub" id="sScatter"></p></div>
    </div>
    <div class="scctl">
      <div><span class="flabel" id="lScG">Agrupar por</span><div class="seg small" id="fScG" role="group" aria-labelledby="lScG"></div></div>
      <div><span class="flabel" id="lScP">Cada ponto</span><div class="seg small" id="fScP" role="group" aria-labelledby="lScP"></div></div>
      <div><span class="flabel" id="lScY">Eixo vertical</span><div class="seg small" id="fScY" role="group" aria-labelledby="lScY"></div></div>
    </div>
    <div class="chart tall"><canvas id="cScatter" role="img" aria-label="Dispersão entre área queimada e emissão"></canvas></div>
    <p class="matrix-note" id="scHint"></p>
    <h3 class="sch3">Maiores anomalias</h3>
    <ul class="anom" id="scAnom"></ul>
    <div class="matrix-wrap" style="margin-top:10px"><table class="matrix sctab" id="scTab"></table></div>
  </section>

  <section class="card" style="margin-bottom:16px">
    <h2>Emissão por hectare queimado: bioma × mês do ano</h2>
    <p class="sub" id="sSeason"></p>
    <div class="matrix-wrap"><table class="matrix" id="mxSeason"></table></div>
    <p class="matrix-note">Mostra em que época do ano o fogo atinge vegetação com mais carbono em cada bioma. Ex.: na Amazônia, a emissão por hectare sobe na estação seca, quando o fogo chega à floresta.</p>
  </section>

  <section class="card" style="margin-bottom:16px" id="extCard" hidden>
    <h2>Comparação com outras bases</h2>
    <p class="sub" id="sExt"></p>
    <div class="seg small" id="fExt" role="group" aria-label="Variável comparada" style="margin:6px 0 8px"></div>
    <ul class="legend" id="lgExt"></ul>
    <div class="chart"><canvas id="cExt" role="img" aria-label="Comparação anual com bases externas"></canvas></div>
    <p class="matrix-note" id="extNote"></p>
  </section>

  <section class="card" style="margin-bottom:16px">
    <h2>Mês × ano</h2>
    <p class="sub" id="sMxMonth"></p>
    <div class="matrix-wrap"><table class="matrix" id="mxMonth"></table></div>
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
      <li>Emissão por hectare queimado = Σ emissão (t) ÷ Σ área queimada (ha) do recorte. Mede a intensidade da queima
        (depende do tipo de vegetação que queimou).</li>
      <li>Emissão por hectare de território = Σ emissão (t) ÷ Σ área total do território do recorte (bioma, UF ou a interseção
        dos dois), queimado ou não, em ha. Mede o peso do fogo na região e permite comparar recortes de tamanhos diferentes.
        As duas se relacionam assim: por ha de território = por ha queimado × fração do território que queimou.</li>
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
        <a href="#m-visao">00 visão geral</a><a href="#m-fontes">01 dados</a><a href="#m-pixel">02 pixel queimado</a><a href="#m-carbono">03 carbono queimado</a>
        <a href="#m-biomassa">04 biomassa</a><a href="#m-gases">05 gases</a><a href="#m-calc">06 simule</a>
        <a href="#m-tabelas">07 estatísticas</a><a href="#m-fluxo">08 processo</a><a href="#m-limites">09 escopo</a><a href="#m-incerteza">10 incerteza</a>
      </nav>
    </div>

    <section class="msec" id="m-visao">
      <div class="mnum">00 / visão geral</div>
      <h3>Do fogo ao número, em seis etapas.</h3>
      <p>Cada pixel queimado no mês passa pela mesma sequência de operações. As seções seguintes detalham cada etapa.</p>
      __SVG_OVERVIEW__
    </section>

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
      __SVG_LAYERS__
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
      __SVG_POOLS__
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
      __SVG_MASS__
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
        mês a mês. Duas medidas relativas ajudam a ler esses totais: a emissão por hectare queimado mostra a intensidade da queima,
        e a emissão por hectare de território mostra o peso do fogo em cada região.</p>
      __SVG_AGG__
      __SVG_DENS__
    </section>

    <section class="msec" id="m-fluxo">
      <div class="mnum">08 / processo</div>
      <h3>Um processo reprodutível, do satélite ao painel.</h3>
      __SVG_PROCESS__
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

    <section class="msec" id="m-incerteza">
      <div class="mnum">10 / incerteza</div>
      <h3>Uma faixa, não só um número.</h3>
      <p>Cada parâmetro da cadeia tem incerteza própria. Como a emissão é um produto de fatores, os desvios relativos se combinam
        em quadratura para cada classe e gás, e a faixa de 95% segue uma distribuição log-normal. Os erros dos parâmetros são
        tratados como sistemáticos, isto é, iguais em todos os pixels de uma classe, o que torna a faixa conservadora.</p>
      <div class="mcard"><div class="k">desvio relativo de cada componente</div><div style="overflow-x:auto"><table class="mtab" id="mUnc"></table></div></div>
      <p class="note" id="mUncTot" style="margin-top:10px;font-size:13.5px;color:var(--ink-2)"></p>
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
  if (a >= 1e6) return [nf(a >= 1e8 ? 0 : a >= 1e7 ? 1 : 2).format(t / 1e6), 'milhões de t'];
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
const fullVal = v => v === null || v === undefined ? '—' : nf(S.measure === 'dens' || S.measure === 'int' ? 2 : 0).format(v);
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
// fatores de incerteza (IC 95%, log-normal) por classe e gás
const UZ = DATA.unc.z;
const ULO = DATA.unc.sig.map(r => r.map(sg => Math.exp(-UZ * sg)));
const UHI = DATA.unc.sig.map(r => r.map(sg => Math.exp(UZ * sg)));
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
const N4_COVER = N4.map(n => CLASS_COVER[DATA.classes.findIndex(c => c['Nível 4'] === n)]);
// modos de detalhamento da série mensal: chave por linha de fato, rótulos e cores
const FOLD = 7;
// UFs: um matiz por região, tons do mesmo matiz dentro da região (ordem fixa, não depende do ranking)
const REGIONS = [['Norte', 135, ['AC', 'AM', 'AP', 'PA', 'RO', 'RR', 'TO']],
  ['Nordeste', 30, ['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE']],
  ['Centro-Oeste', 350, ['DF', 'GO', 'MS', 'MT']], ['Sudeste', 215, ['ES', 'MG', 'RJ', 'SP']], ['Sul', 270, ['PR', 'RS', 'SC']]];
const UF_COLOR = [], UF_ORDER = [];
DATA.ufs.forEach((u, k) => {
  REGIONS.forEach(([, hue, list], r) => {
    const j = list.indexOf(u.sigla);
    if (j < 0) return;
    const l = list.length > 1 ? 28 + 44 * j / (list.length - 1) : 45;
    UF_COLOR[k] = 'hsl(' + hue + ' 55% ' + l.toFixed(0) + '%)'; UF_ORDER[k] = r * 100 + j;
  });
  if (UF_COLOR[k] === undefined) { UF_COLOR[k] = '#9c8f80'; UF_ORDER[k] = 999; }
});
const DETAIL = {
  cover: { n: () => NC, key: i => CLASS_COVER[F.c[i]], label: k => COVER[k][0], color: k => coverColor(k) },
  n0: { n: () => 2, key: i => IS_NAT[F.c[i]] ? 0 : 1, label: k => ['Vegetação nativa', 'Agropecuária'][k],
        color: k => css(k === 0 ? '--nat' : '--ant') },
  n4: { n: () => N4.length, key: i => CLASS_N4[F.c[i]], label: k => N4[k], color: k => N4_COLOR[k], order: k => N4_COVER[k] },
  biome: { n: () => NB, key: i => F.b[i], label: k => BIOMES[k], color: k => biomeColor(k) },
  uf: { n: () => DATA.ufs.length, key: i => F.u[i], label: k => DATA.ufs[k].sigla, color: k => UF_COLOR[k], order: k => UF_ORDER[k] },
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
const MEASURE_HINT = {
  area: ['Σ área queimada (ha)', 'Hectares queimados no recorte e no período.'],
  emiss: ['Σ emissão do gás (t)', 'Toneladas emitidas no recorte e no período.'],
  int: ['Σ emissão do gás (t) ÷ Σ área queimada (ha)', 'Quanto cada hectare que pegou fogo emitiu, em média. Mede a intensidade da queima: depende do tipo de vegetação, não de quanto queimou.'],
  dens: ['Σ emissão do gás (t) ÷ Σ área do território (ha)', 'Emissão por hectare do território inteiro do recorte (estado, bioma ou os dois), queimado ou não. Mede o peso do fogo na região e compara regiões de tamanhos diferentes.'],
};
function paintMeasureHint() {
  const h = $('fMeasureHint'), [f, t] = MEASURE_HINT[S.measure]; h.textContent = '';
  const b = document.createElement('b'); b.className = 'fx'; b.textContent = f; h.append(b, document.createTextNode(t));
}
seg('fMeasure', 'measure', [['area', 'Área queimada', 'Σ área queimada (ha)'], ['emiss', 'Emissão', 'Σ emissão do gás (t)'],
  ['int', 'Por ha queimado', 'Σ emissão (t) ÷ Σ área queimada (ha)'], ['dens', 'Por ha de território', 'Σ emissão (t) ÷ Σ área do território (ha)']],
  () => { paintMeasureHint(); renderAll(); });
paintMeasureHint();
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

// área do território (ha) por bioma × UF (o CSV vem em km²; 1 km² = 100 ha)
const TERR = BIOMES.map(() => new Float64Array(DATA.ufs.length));
DATA.territory.forEach(([b, u, km2]) => { TERR[b][u] = km2 * 100; });
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
    gas: [0, 0, 0], A: 0, E: 0, Elo: 0, Ehi: 0,
    mLo: new Float64Array(NM), mHi: new Float64Array(NM),
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
    const lo = ULO[F.c[i]], hi = UHI[F.c[i]];
    const eLo = g === 'total' ? c2 * lo[0] + c4 * lo[1] + n2 * lo[2] : g === 'co2' ? c2 * lo[0] : g === 'ch4' ? c4 * lo[1] : n2 * lo[2];
    const eHi = g === 'total' ? c2 * hi[0] + c4 * hi[1] + n2 * hi[2] : g === 'co2' ? c2 * hi[0] : g === 'ch4' ? c4 * hi[1] : n2 * hi[2];
    R.mLo[m] += eLo; R.mHi[m] += eHi;
    R.mA[m * NB + b] += a; R.mE[m * NB + b] += e;
    R.mG[m * 3] += c2; R.mG[m * 3 + 1] += c4; R.mG[m * 3 + 2] += n2;
    const ck = CLASS_COVER[F.c[i]]; R.mCA[m * NC + ck] += a; R.mCE[m * NC + ck] += e;
    const dk = dKey(i); R.dA[m * R.nD + dk] += a; R.dE[m * R.nD + dk] += e;
    if (m < m0 || m > m1) continue;
    R.A += a; R.E += e; R.Elo += eLo; R.Ehi += eHi;
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
// por hectare queimado: E ÷ área queimada; nas partes empilhadas, o denominador (Aden) é a área do recorte inteiro
function measureOf(A, E, T, Aden) {
  const ms = S.measure;
  if (ms === 'area') return A;
  if (ms === 'emiss') return E;
  if (ms === 'int') { const d = Aden === undefined ? A : Aden; return d > 0 ? E / d : null; }
  return T > 0 ? E / T : null;
}
const isRatio = () => S.measure === 'dens' || S.measure === 'int';
function measureUnit() {
  const ms = S.measure, g = GAS[S.gas];
  return ms === 'area' ? 'ha' : ms === 'emiss' ? g.unit : ms === 'int' ? g.unit + '/ha queimado' : g.unit + '/ha de território';
}
function measureName() {
  const ms = S.measure, g = GAS[S.gas];
  return ms === 'area' ? 'Área queimada' : ms === 'emiss' ? 'Emissão de ' + g.name
    : ms === 'int' ? 'Emissão de ' + g.name + ' por hectare queimado' : 'Emissão de ' + g.name + ' por hectare de território';
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
// rótulo de valor nas barras de série única (some se não couber na largura da barra)
const shortVal = v => {
  const a = Math.abs(v);
  if (S.measure === 'dens' || S.measure === 'int') return nf(a < 10 ? 2 : a < 100 ? 1 : 0).format(v);
  if (a >= 1e6) return nf(a < 1e8 ? 1 : 0).format(v / 1e6) + ' mi';
  if (a >= 1e3) return nf(a < 1e5 ? 1 : 0).format(v / 1e3) + ' mil';
  return nf(a < 10 ? 1 : 0).format(v);
};
const barLabels = {
  id: 'barLabels',
  afterDatasetsDraw(ch) {
    const ds = ch.data.datasets;
    const hor = ch.options.indexAxis === 'y', ctx = ch.ctx, area = ch.chartArea;
    ctx.save();
    // barras de incerteza (dataset.err = [[lo, hi], ...])
    const tops = {};
    ds.forEach((d, di) => {
      if (!d.err || hor) return;
      const sc = ch.scales.y;
      ctx.strokeStyle = css('--ink'); ctx.lineWidth = 1.2;
      ch.getDatasetMeta(di).data.forEach((bar, i) => {
        const r = d.err[i]; if (!r) return;
        const y0 = sc.getPixelForValue(r[0]), y1 = sc.getPixelForValue(r[1]), cw = Math.min(8, bar.width / 2);
        ctx.beginPath(); ctx.moveTo(bar.x, y0); ctx.lineTo(bar.x, y1);
        ctx.moveTo(bar.x - cw / 2, y0); ctx.lineTo(bar.x + cw / 2, y0);
        ctx.moveTo(bar.x - cw / 2, y1); ctx.lineTo(bar.x + cw / 2, y1); ctx.stroke();
        tops[di + ':' + i] = y1;
      });
    });
    if (ds.length !== 1) { ctx.restore(); return; }
    ctx.font = '600 11px ' + getComputedStyle(document.body).fontFamily;
    ctx.fillStyle = css('--ink-2');
    const slot = hor ? 0 : (area.right - area.left) / Math.max(1, ch.data.labels.length);
    ch.getDatasetMeta(0).data.forEach((bar, i) => {
      const v = ds[0].data[i];
      if (v === null || v === undefined || !(v > 0)) return;
      const t = shortVal(v), w = ctx.measureText(t).width;
      if (hor) {
        if (bar.height < 10) return;
        ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
        ctx.fillText(t, Math.min(bar.x + 5, area.right + 56 - w), bar.y);
      } else {
        if (w > slot - 4) return;
        ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
        const top = tops['0:' + i];
        ctx.fillText(t, bar.x, (top !== undefined ? Math.min(top, bar.y) : bar.y) - 3);
      }
    });
    ctx.restore();
  },
};
function makeBar(canvas, horizontal) {
  return new Chart(canvas, {
    type: 'bar',
    data: { labels: [], datasets: [] },
    plugins: [barLabels],
    options: {
      layout: { padding: horizontal ? { right: 58 } : { top: 16 } },
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
        ? { x: { beginAtZero: true, ticks: { callback: axisTick, maxTicksLimit: 5, maxRotation: 0 } }, y: { grid: { display: false } } }
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
  if (D.order) keys.sort((x, y) => (D.order(x) - D.order(y)) || (tot[y] - tot[x]));
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
  const aTot = {}; idx.forEach(m => { let s = 0; for (let k = 0; k < nD; k++) s += R.dA[m * nD + k]; aTot[m] = s; });
  cMonthly.data.datasets = series.map(sr => ({
    label: sr.label, data: idx.map(m => measureOf(sr.A(m), sr.E(m), R.T, aTot[m])),
    ...barStyle(sr.color, { seam, flat: true }),
  }));
  cMonthly.options.scales.x.stacked = cMonthly.options.scales.y.stacked = true;
  legend($('lgMonthly'), series.map(sr => [sr.label, sr.color]));
  const how = { cover: 'cobertura do solo (cores MapBiomas)', n0: 'vegetação nativa × agropecuária',
    n4: 'classe detalhada (cores MapBiomas)', biome: 'bioma',
    uf: 'UF (tons por região: Norte verde, Nordeste laranja, Centro-Oeste rosa, Sudeste azul, Sul roxo)' }[S.group];
  $('sMonthly').textContent = measureName() + ' (' + measureUnit() + '), empilhado por ' + how
    + (S.measure === 'int' ? ' · cada parte = sua emissão ÷ área queimada total do mês' : '');
  cMonthly.options.plugins.tooltip.callbacks.title = items => mLong(MONTHS[idx[items[0].dataIndex]]);
  cMonthly.options.plugins.tooltip.callbacks.footer = items => {
    if (items.length < 2) return '';
    const t = items.reduce((s, it) => s + (it.parsed.y || 0), 0);
    return 'Total: ' + fullVal(t) + ' ' + measureUnit();
  };
  cMonthly.options.plugins.tooltip.itemSort = (x, y) => (y.parsed.y || 0) - (x.parsed.y || 0);
  cMonthly.options.plugins.tooltip.filter = it => (it.parsed.y || 0) > 0;
  $('tMonthly').textContent = ms === 'area' ? 'Área queimada por mês' : ms === 'dens' ? 'Emissão por hectare de território, por mês'
    : ms === 'int' ? 'Emissão por hectare queimado, por mês' : 'Emissões por mês';
  themeChart(cMonthly); cMonthly.update();
}

function renderAnnual(R) {
  const bSel = S.biome === 'all' ? -1 : +S.biome;
  const showUnc = S.measure === 'emiss' || S.measure === 'dens';
  const err = [];
  const vals = YEARS.map(y => {
    let a = 0, e = 0, lo = 0, hi = 0;
    MONTHS.forEach((m, i) => { if (m.startsWith(y)) { const [ma, me] = monthSum(R, i); a += ma; e += me; lo += R.mLo[i]; hi += R.mHi[i]; } });
    const f = S.measure === 'dens' ? (R.T > 0 ? 1 / R.T : 0) : 1;
    err.push(showUnc && e > 0 ? [lo * f, hi * f] : null);
    return measureOf(a, e, R.T);
  });
  cAnnual.data.labels = YEARS.map(y => y === LAST.slice(0, 4) && LAST_YEAR_PARTIAL ? y + '*' : y);
  cAnnual.data.datasets = [{ label: measureName(), data: vals, err: showUnc ? err : null,
    ...barStyle(bSel >= 0 ? biomeColor(bSel) : css('--accent')) }];
  const his = err.filter(Boolean).map(r => r[1]);
  cAnnual.options.scales.y.suggestedMax = showUnc && his.length ? Math.max(...his) * 1.1 : undefined;
  cAnnual.options.plugins.tooltip.callbacks.afterLabel = c => {
    const r = err[c.dataIndex]; return showUnc && r ? ' faixa (95%): ' + fullVal(r[0]) + ' a ' + fullVal(r[1]) : '';
  };
  cAnnual.options.scales.x.stacked = cAnnual.options.scales.y.stacked = false;
  $('sAnnual').textContent = measureName() + ' (' + measureUnit() + '), todos os anos'
    + (showUnc ? ' · traço: faixa de incerteza (95%)' : '')
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
  subEl.textContent = measureName() + ' (' + measureUnit() + ') ' + what + (S.measure === 'dens' && note ? ' · ' + note : '')
    + (S.measure === 'int' ? ' · emissão ÷ área queimada de cada linha' : '');
  themeChart(chart); chart.update();
  return rows.length;
}
function renderClass(R) {
  const labels = Object.keys(R.cA);
  renderRanked(cClass, labels, labels.map(k => R.cA[k]), labels.map(k => R.cE[k]), labels.map(() => R.T), $('sClass'),
    'por classe', 'contribuição de cada classe para a emissão por ha de território do recorte',
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
  const u = $('kEmissUnc'); u.textContent = '';
  if (R.E > 0) {
    const b = document.createElement('b'); b.textContent = fmtT(R.Elo).join(' ') + ' a ' + fmtT(R.Ehi).join(' ');
    u.append(document.createTextNode('faixa de incerteza (95%): '), b);
  }
  $('kIntLabel').textContent = 'Emissão por hectare queimado';
  const tu = S.gas === 'co2' ? 't CO₂' : 't CO₂e';
  setValue($('kInt'), R.A > 0 ? nf(R.E / R.A >= 100 ? 0 : 1).format(R.E / R.A) : '—', tu + '/ha');
  $('kIntNote').textContent = 'Σ emissão (t) ÷ Σ área queimada (' + fmtHa(R.A).join(' ') + ')';
  setValue($('kArea'), ...fmtHa(R.A));
  $('kAreaNote').textContent = R.T > 0 ? nf(1).format(R.A / R.T * 100) + '% do território do recorte' : '';
  $('kDensLabel').textContent = 'Emissão por hectare de território';
  setValue($('kDens'), R.T > 0 ? new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(R.E / R.T) : '—',
    tu + '/ha');
  $('kDensNote').textContent = 'Σ emissão (t) ÷ Σ área do território (' + fmtHa(R.T).join(' ') + '), queimado ou não';

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
  const gwp = DATA.method.gwp;
  const co2e = R.gas, mass = [R.gas[0], R.gas[1] / gwp.CH4, R.gas[2] / gwp.N2O];
  const names = ['CO₂', 'CH₄', 'N₂O'], cols = ['--g-co2', '--g-ch4', '--g-n2o'].map(css);
  const tE = co2e[0] + co2e[1] + co2e[2], tM = mass[0] + mass[1] + mass[2];
  const bars = $('gasBars'); bars.textContent = '';
  [['em massa', mass, tM], ['em CO₂e', co2e, tE]].forEach(([lab, v, t]) => {
    const row = document.createElement('div'); row.className = 'gasbar';
    const l = document.createElement('span'); l.textContent = lab;
    const tr = document.createElement('div'); tr.className = 't';
    v.forEach((x, j) => { const sp = document.createElement('span'); sp.style.flex = String(t > 0 ? x / t : 0); sp.style.background = cols[j];
      sp.title = names[j] + ' ' + lab + ': ' + nf(2).format(t > 0 ? x / t * 100 : 0) + '%'; tr.appendChild(sp); });
    row.append(l, tr); bars.appendChild(row);
  });
  const fm = t => { const a = Math.abs(t); return a >= 1e6 ? nf(a >= 1e8 ? 0 : 1).format(t / 1e6) + ' mi t' : a >= 1e3 ? nf(a >= 1e5 ? 0 : 1).format(t / 1e3) + ' mil t' : nf(0).format(t) + ' t'; };
  const tb = $('gasTab'); tb.textContent = '';
  const hr = tb.createTHead().insertRow();
  ['Gás', 'Massa', '× GWP', 'CO₂e', '% CO₂e'].forEach(h => { const th = document.createElement('th'); th.textContent = h; th.scope = 'col'; hr.appendChild(th); });
  const body = tb.createTBody();
  names.forEach((n, j) => {
    const tr = body.insertRow();
    const c0 = tr.insertCell(); const sw = document.createElement('i'); sw.style.background = cols[j]; c0.append(sw, document.createTextNode(n));
    tr.insertCell().textContent = fm(mass[j]);
    tr.insertCell().textContent = j === 0 ? '1' : String(j === 1 ? gwp.CH4 : gwp.N2O);
    tr.insertCell().textContent = fm(co2e[j]);
    tr.insertCell().textContent = tE > 0 ? nf(1).format(co2e[j] / tE * 100) + '%' : '—';
  });
  const nonCO2 = tE > 0 ? (co2e[1] + co2e[2]) / tE * 100 : 0;
  $('gasNote').textContent = tE > 0 ? 'CH₄ e N₂O são ' + nf(2).format((mass[1] + mass[2]) / tM * 100) + '% da massa emitida, mas '
    + nf(1).format(nonCO2) + '% do efeito (CO₂e). A proporção varia com a vegetação: florestas emitem mais CH₄ por kg queimado.' : '';

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
  return ms === 'emiss' ? 'milhões de t ' + g.unit.slice(2) : ms === 'area' ? 'mil ha'
    : ms === 'int' ? g.unit + ' por ha queimado' : g.unit + ' por ha de território';
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
function renderMonthMatrix(R) {
  const rows = MON.map((mo, k) => {
    const A = new Float64Array(NY), E = new Float64Array(NY);
    MONTHS.forEach((ym, i) => { if (+ym.slice(5) - 1 !== k) return; const [a, e] = monthSum(R, i); A[YEAR_OF[i]] = a; E[YEAR_OF[i]] = e; });
    return { label: mo, A, E, T: R.T };
  });
  renderMatrix('mxMonth', 'Mês', rows, R.T);
  $('sMxMonth').textContent = measureName() + ' (' + matrixUnit() + ') · ' + sliceText().replace(/ · [^·]+ a [^·]+$/, '')
    + ' · sazonalidade: cada coluna é um ano · ignora o filtro de período';
}
let cScatter = null;
const logTick = v => { const l = Math.log10(v); return Math.abs(l - Math.round(l)) < 1e-6 ? axisTick(v) : ''; };
const SC = { g: 'uf', p: 'year', y: 'e', hi: null };
function withAlpha(c, a) {
  const cx = withAlpha.cx || (withAlpha.cx = document.createElement('canvas').getContext('2d'));
  cx.fillStyle = '#000'; cx.fillStyle = c; const h = cx.fillStyle;
  if (h[0] === '#') { const n = parseInt(h.slice(1), 16); return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')'; }
  return h.replace(/rgba?\(([^)]+)\)/, (m, x) => 'rgba(' + x.split(',').slice(0, 3).join(',') + ',' + a + ')');
}
function scSeg(id, key, items) {
  const box = $(id); box.textContent = '';
  items.forEach(([v, t, title]) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = t; if (title) b.title = title;
    b.setAttribute('aria-pressed', String(SC[key] === v));
    b.addEventListener('click', () => { if (SC[key] === v) return; SC[key] = v; SC.hi = null; renderScatter(); }); box.appendChild(b); });
}
// pontos: entidade (UF, bioma ou cobertura) × período (ano ou mês); respeita bioma, UF, cobertura, período e gás
// dimensões da dispersão: chave por linha de fato, quantidade, rótulo, cor e nome
const SC_DIMS = {
  uf: { n: () => NU, key: (i, m) => F.u[i], label: k => DATA.ufs[k].sigla, full: k => DATA.ufs[k].nome, color: k => UF_COLOR[k],
        name: 'UF', art: 'uma' },
  biome: { n: () => NB, key: (i, m) => F.b[i], label: k => BIOMES[k], color: k => biomeColor(k), name: 'bioma', art: 'um' },
  cover: { n: () => NC, key: (i, m) => CLASS_COVER[F.c[i]], label: k => COVER[k][0], color: k => coverColor(k),
           name: 'classe de cobertura', art: 'uma' },
  year: { n: () => NY, key: (i, m) => YEAR_OF[m], label: k => YEARS[k] + (YEARS[k] === LAST.slice(0, 4) && LAST_YEAR_PARTIAL ? '*' : ''),
          color: k => rampAt(rampColors(), 0.25 + 0.75 * k / Math.max(1, NY - 1)).color, name: 'ano', art: 'um' },
  mon: { n: () => 12, key: (i, m) => +MONTHS[m].slice(5) - 1, label: k => MON[k], full: k => MON[k],
         color: k => 'hsl(' + ((k * 30 + 200) % 360) + ' 55% 45%)', name: 'mês do ano', art: 'um' },
  ym: { n: () => NM, key: (i, m) => m, label: k => mLabel(MONTHS[k]), color: () => css('--accent'), name: 'mês', art: 'um' },
};
// para cada agrupamento, o que pode ser ponto
const SC_POINTS = {
  uf: [['year', 'Ano'], ['ym', 'Mês']], biome: [['year', 'Ano'], ['ym', 'Mês']], cover: [['year', 'Ano'], ['ym', 'Mês']],
  year: [['uf', 'UF'], ['biome', 'Bioma'], ['cover', 'Cobertura'], ['ym', 'Mês']],
  mon: [['uf', 'UF'], ['biome', 'Bioma'], ['cover', 'Cobertura'], ['year', 'Ano']],
};
// pontos: entidade × ponto; respeita bioma, UF, cobertura, período e gás
function scatterData() {
  const [m0, m1] = monthRange();
  const bSel = S.biome === 'all' ? -1 : +S.biome, uSel = S.uf === 'all' ? -1 : +S.uf, g = S.gas;
  const G = SC_DIMS[SC.g], P = SC_DIMS[SC.p];
  const nE = G.n(), nP = P.n();
  const A = new Float64Array(nE * nP), E = new Float64Array(nE * nP);
  for (let i = 0; i < N; i++) {
    const m = F.m[i]; if (m < m0 || m > m1) continue;
    const b = F.b[i], u = F.u[i];
    if (bSel >= 0 && b !== bSel) continue;
    if (SC.g !== 'uf' && uSel >= 0 && u !== uSel) continue;
    if (!coverPass(F.c[i])) continue;
    const k = G.key(i, m), t = P.key(i, m);
    const e = g === 'total' ? F.co2[i] + F.ch4[i] + F.n2o[i] : F[g][i];
    A[k * nP + t] += F.a[i]; E[k * nP + t] += e;
  }
  const ents = [];
  for (let k = 0; k < nE; k++) {
    const name = G.label(k), full = G.full ? G.full(k) : name, color = G.color(k);
    const pts = [];
    for (let t = 0; t < nP; t++) { const a = A[k * nP + t], e = E[k * nP + t];
      if (a > 0 && e > 0) pts.push({ x: a, y: e, k, per: P.label(t) }); }
    if (!pts.length) continue;
    let sa = 0, se = 0; pts.forEach(q => { sa += q.x; se += q.y; });
    const kk = se / sa;
    // R² em log em torno da reta da própria entidade (y = k·x)
    const ly = pts.map(q => Math.log(q.y)), my = ly.reduce((s, v) => s + v, 0) / ly.length;
    let ss = 0, st = 0; pts.forEach((q, i) => { ss += (ly[i] - Math.log(kk * q.x)) ** 2; st += (ly[i] - my) ** 2; });
    const ratios = pts.map(q => q.y / q.x);
    // reta livre em log: ln(emissão) = ln(a) + b·ln(área); b > 1: o fogo escala para vegetação com mais carbono
    let fit = null;
    if (pts.length >= 4) {
      const lx = pts.map(q => Math.log(q.x)), mx = lx.reduce((s, v) => s + v, 0) / lx.length;
      let sxy = 0, sxx = 0; lx.forEach((v, i) => { sxy += (v - mx) * (ly[i] - my); sxx += (v - mx) ** 2; });
      if (sxx > 0) {
        const b = sxy / sxx, la = my - b * mx;
        let r = 0; lx.forEach((v, i) => { r += (ly[i] - la - b * v) ** 2; });
        const se_b = pts.length > 2 ? Math.sqrt(r / (pts.length - 2) / sxx) : null;
        fit = { a: Math.exp(la), b, r2: st > 0 ? 1 - r / st : null, se: se_b };
      }
    }
    pts.forEach(q => { q.dev = q.y / q.x / kk - 1; q.exc = q.y - kk * q.x; });
    ents.push({ k, name, full, color, pts, sa, se, kk, fit, r2: pts.length > 2 && st > 0 ? 1 - ss / st : null,
      lo: Math.min(...ratios), hi: Math.max(...ratios), sel: SC.g === 'uf' && k === uSel });
  }
  return ents;
}
// rótulos dos maiores desvios na dispersão
const scLabels = {
  id: 'scLabels',
  afterDatasetsDraw(ch) {
    const ctx = ch.ctx; ctx.save();
    ctx.font = '600 11px ' + getComputedStyle(document.body).fontFamily; ctx.fillStyle = css('--ink'); ctx.textBaseline = 'middle';
    const boxes = [];  // evita sobreposição: desloca o rótulo para baixo até achar espaço
    ch.data.datasets.forEach((d, di) => {
      if (d.isLine) return;
      ch.getDatasetMeta(di).data.forEach((el, i) => {
        const q = d.data[i]; if (!q || !q.lab) return;
        const right = el.x < ch.chartArea.right - 150, w = ctx.measureText(q.lab).width;
        const x = el.x + (right ? 8 : -8), x0 = right ? x : x - w;
        let y = el.y;
        while (boxes.some(bx => x0 < bx[0] + bx[2] && x0 + w > bx[0] && Math.abs(y - bx[1]) < 13)) y += 13;
        boxes.push([x0, y, w]);
        if (y !== el.y) { ctx.strokeStyle = css('--muted'); ctx.lineWidth = 0.8; ctx.beginPath(); ctx.moveTo(el.x, el.y); ctx.lineTo(x, y); ctx.stroke(); }
        ctx.textAlign = right ? 'left' : 'right';
        ctx.strokeStyle = css('--surface'); ctx.lineWidth = 3; ctx.strokeText(q.lab, x, y);
        ctx.fillText(q.lab, x, y);
      });
    });
    ctx.restore();
  },
};
const readB = f => !f || f.se === null ? '—' : (f.b - 1.96 * f.se > 1 ? 'escala' : f.b + 1.96 * f.se < 1 ? 'dilui' : 'estável');
function renderScatter() {
  scSeg('fScG', 'g', [['uf', 'UF'], ['biome', 'Bioma'], ['cover', 'Cobertura'], ['year', 'Ano'], ['mon', 'Mês do ano', 'jan, fev, … somando todos os anos']]);
  if (!SC_POINTS[SC.g].some(([v]) => v === SC.p)) SC.p = SC_POINTS[SC.g][0][0];
  scSeg('fScP', 'p', SC_POINTS[SC.g]);
  scSeg('fScY', 'y', [['e', 'Emissão (t)', 'Σ emissão do gás (t), escala log'], ['i', 'Por ha queimado (t/ha)', 'Σ emissão (t) ÷ Σ área queimada (ha)'],
    ['d', 'Desvio da média (%)', 'quanto o ponto emitiu por hectare acima ou abaixo da média do seu grupo']]);
  const ents = scatterData(), gu = GAS[S.gas].unit, Y = SC.y;
  let SA = 0, SE = 0; ents.forEach(en => { SA += en.sa; SE += en.se; });
  const KK = SA > 0 ? SE / SA : 0;
  const allX = ents.flatMap(en => en.pts.map(q => q.x)), X0 = Math.min(...allX), X1 = Math.max(...allX);
  const dim = en => SC.hi !== null && SC.hi !== en.k;
  // maiores anomalias: excesso ou falta de emissão (t) em relação à média do próprio grupo
  const pool = ents.filter(en => SC.hi === null || SC.hi === en.k).flatMap(en => en.pts.map(q => ({ q, en })));
  pool.sort((x, y) => Math.abs(y.q.exc) - Math.abs(x.q.exc));
  const top = new Set(pool.slice(0, 5).map(o => o.q));
  const fmtDev = v => (v >= 0 ? '+' : '') + nf(0).format(v * 100) + '%';
  const yOf = q => Y === 'e' ? q.y : Y === 'i' ? q.y / q.x : q.dev * 100;
  const ds = [];
  ents.forEach(en => {
    const c = dim(en) ? withAlpha(en.color, 0.15) : en.color;
    ds.push({ type: 'scatter', label: en.name, ent: en, order: 2,
      data: en.pts.map(q => ({ ...q, y: yOf(q), e: q.y, lab: top.has(q) ? en.name + ' · ' + q.per + ': ' + fmtDev(q.dev) : '' })),
      backgroundColor: c, borderColor: dim(en) ? 'transparent' : css('--surface'), borderWidth: 1,
      pointRadius: en.pts.map(q => top.has(q) ? 6 : en.sel || SC.hi === en.k ? 5.5 : SC.p === 'ym' ? 3 : 4), pointHoverRadius: 7 });
    if (!en.fit || Y === 'd') return;
    const x0 = Math.min(...en.pts.map(q => q.x)), x1 = Math.max(...en.pts.map(q => q.x));
    const line = [];
    for (let j = 0; j <= 12; j++) { const x = x0 * Math.pow(x1 / x0, j / 12), ye = en.fit.a * Math.pow(x, en.fit.b);
      line.push({ x, y: Y === 'e' ? ye : ye / x }); }
    ds.push({ type: 'line', label: en.name + ' (reta)', data: line, ent: en, isLine: true, order: 1, pointRadius: 0, tension: 0,
      borderColor: dim(en) ? withAlpha(en.color, 0.12) : en.color, borderWidth: SC.hi === en.k ? 3 : 2 });
  });
  if (Y === 'd') ds.push({ type: 'line', label: 'média do grupo', data: allX.length ? [{ x: X0, y: 0 }, { x: X1, y: 0 }] : [],
    borderColor: css('--ink'), borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, order: 0, isLine: true, isAll: true });
  else ds.push({ type: 'line', label: 'todos', data: allX.length ? [{ x: X0, y: Y === 'e' ? KK * X0 : KK }, { x: X1, y: Y === 'e' ? KK * X1 : KK }] : [],
    borderColor: css('--ink'), borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, order: 0, isLine: true, isAll: true });
  if (!cScatter) {
    cScatter = new Chart($('cScatter'), { type: 'scatter', data: { datasets: [] }, plugins: [scLabels], options: {
      responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: {} } },
      onClick: (ev, els) => { const d = els.length ? cScatter.data.datasets[els[0].datasetIndex] : null;
        SC.hi = d && d.ent ? (SC.hi === d.ent.k ? null : d.ent.k) : null; renderScatter(); },
      scales: { x: { type: 'logarithmic', title: { display: true, text: '' }, ticks: { callback: logTick, maxRotation: 0, autoSkip: false } },
                y: { type: 'logarithmic', title: { display: true, text: '' }, ticks: { callback: logTick } } } } });
  }
  cScatter.data.datasets = ds;
  cScatter.options.scales.y.type = Y === 'e' ? 'logarithmic' : 'linear';
  cScatter.options.scales.y.beginAtZero = Y === 'i';
  cScatter.options.scales.y.ticks.callback = Y === 'e' ? logTick : Y === 'i' ? v => nf(0).format(v) : v => (v > 0 ? '+' : '') + nf(0).format(v) + '%';
  cScatter.options.scales.x.title.text = 'Σ área queimada (ha, escala log)';
  cScatter.options.scales.y.title.text = Y === 'e' ? 'Σ emissão (' + gu + ', escala log)' : Y === 'i' ? 'Σ emissão ÷ Σ área queimada (' + gu + '/ha)'
    : 't/ha do ponto ÷ t/ha do seu grupo − 1 (%)';
  cScatter.options.plugins.tooltip.callbacks.label = c => {
    const d = c.dataset;
    if (d.isAll) return Y === 'd' ? ' média do grupo (0%)' : ' todos: ' + nf(1).format(KK) + ' ' + gu + '/ha';
    if (d.isLine) return ' reta ' + d.ent.name + ': b = ' + nf(2).format(d.ent.fit.b) + ' (' + readB(d.ent.fit) + ')';
    const q = c.raw;
    return ' ' + d.ent.name + ' · ' + q.per + ': ' + fmtHa(q.x).join(' ') + ' · ' + fmtT(q.e).join(' ') + ' · '
      + nf(1).format(q.e / q.x) + ' ' + gu + '/ha (' + fmtDev(q.dev) + ' vs média do grupo)';
  };
  themeChart(cScatter);
  ['x', 'y'].forEach(a => { cScatter.options.scales[a].title.color = css('--muted'); });
  cScatter.update();

  const gName = SC_DIMS[SC.g].name, pName = SC_DIMS[SC.p].name, pd = SC_DIMS[SC.p];
  $('tScatter').textContent = Y === 'e' ? 'Área queimada × emissão' : Y === 'i' ? 'Área queimada × emissão por hectare queimado'
    : 'Desvio da emissão por hectare em relação à média do grupo';
  $('sScatter').textContent = 'Cada ponto é ' + pd.art + ' ' + pName + ' dentro de ' + SC_DIMS[SC.g].art + ' ' + gName
    + (Y === 'd' ? ' · 0% = a média do próprio grupo (Σ emissão ÷ Σ área)'
      : ' · cada ' + gName + ' tem a sua reta ajustada: emissão = a · área^b · tracejada: todos (' + nf(1).format(KK) + ' ' + gu + '/ha)')
    + ' · rótulos: as 5 maiores anomalias em toneladas';
  $('scHint').textContent = Y === 'e'
    ? 'Leia a inclinação de cada reta (b). b > 1: quando o fogo cresce, ele avança para vegetação com mais carbono por hectare (escala). '
      + 'b < 1: os meses ou anos grandes se espalham por vegetação mais pobre (dilui). b ≈ 1: a emissão por hectare não depende do tamanho do fogo. '
      + 'A altura da reta é a emissão por hectare; a distância vertical entre duas retas é a razão entre elas.'
    : Y === 'i' ? 'Mesma reta, vista em t/ha: subindo para a direita, o fogo escala; descendo, dilui; plana, estável.'
      : 'Pontos acima de 0% emitiram mais por hectare do que o normal do seu grupo: queimou vegetação com mais carbono que o habitual.';

  // tabela: uma linha por entidade
  const tb = $('scTab'); tb.textContent = '';
  const hr = tb.createTHead().insertRow();
  [gName[0].toUpperCase() + gName.slice(1), 'Pontos', 'Σ área queimada (ha)', 'Σ emissão (t)', 'Σ emissão ÷ Σ área (' + gu + '/ha)',
   'Faixa dos pontos (t/ha)', 'Inclinação b (± IC 95%)', 'Quando o fogo cresce', 'R² (log)']
    .forEach(h => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = h; hr.appendChild(th); });
  const body = tb.createTBody(), maxK = Math.max(...ents.map(en => en.kk));
  const timeG = SC.g === 'year' || SC.g === 'mon';  // tempo: ordem cronológica; demais: pela inclinação
  [...ents].sort((x, y) => timeG ? x.k - y.k : ((y.fit ? y.fit.b : 0) - (x.fit ? x.fit.b : 0))).forEach(en => {
    const tr = body.insertRow(); if (SC.hi !== null) tr.className = SC.hi === en.k ? 'on' : 'dim';
    tr.tabIndex = 0; tr.title = 'Destacar ' + en.full;
    const th = document.createElement('th'); th.scope = 'row'; const i = document.createElement('i'); i.style.background = en.color;
    th.append(i, document.createTextNode(en.name)); tr.appendChild(th);
    tr.insertCell().textContent = String(en.pts.length);
    tr.insertCell().textContent = nf(0).format(en.sa);
    tr.insertCell().textContent = nf(0).format(en.se);
    const kc = tr.insertCell(); const bar = document.createElement('span'); bar.className = 'kbar'; bar.style.width = (40 * en.kk / maxK).toFixed(1) + 'px';
    bar.style.background = en.color; kc.append(bar, document.createTextNode(nf(1).format(en.kk)));
    tr.insertCell().textContent = nf(1).format(en.lo) + ' a ' + nf(1).format(en.hi);
    const f = en.fit;
    tr.insertCell().textContent = !f ? '—' : nf(2).format(f.b) + (f.se !== null ? ' ± ' + nf(2).format(1.96 * f.se) : '');
    const rd = tr.insertCell(); const lab = readB(f); rd.textContent = lab; rd.className = 'rd-' + (lab === 'escala' ? 'up' : lab === 'dilui' ? 'down' : 'eq');
    tr.insertCell().textContent = !f || f.r2 === null ? '—' : nf(2).format(f.r2);
    const pick = () => { SC.hi = SC.hi === en.k ? null : en.k; renderScatter(); };
    tr.addEventListener('click', pick); tr.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); } });
  });
  const tf = tb.createTFoot().insertRow();
  const fth = document.createElement('th'); fth.scope = 'row'; fth.textContent = 'Todos'; tf.appendChild(fth);
  tf.insertCell().textContent = String(ents.reduce((s, en) => s + en.pts.length, 0));
  tf.insertCell().textContent = nf(0).format(SA); tf.insertCell().textContent = nf(0).format(SE);
  tf.insertCell().textContent = nf(1).format(KK); ['', '', '', ''].forEach(t => { tf.insertCell().textContent = t; });

  // lista das maiores anomalias
  const an = $('scAnom'); an.textContent = '';
  pool.slice(0, 5).forEach(({ q, en }) => {
    const li = document.createElement('li'); const i = document.createElement('i'); i.style.background = en.color;
    const b = document.createElement('b'); b.textContent = en.name + ' · ' + q.per;
    li.append(i, b, document.createTextNode(': ' + nf(1).format(q.y / q.x) + ' ' + gu + '/ha, ' + fmtDev(q.dev) + ' vs a média do grupo ('
      + nf(1).format(en.kk) + ') → ' + (q.exc >= 0 ? '+' : '−') + fmtT(Math.abs(q.exc)).join(' ') + ' em relação ao esperado'));
    an.appendChild(li);
  });
}

// ---------- matriz: emissão por hectare queimado, bioma × mês do ano ----------
function renderSeasonIntensity() {
  const [m0, m1] = monthRange();
  const uSel = S.uf === 'all' ? -1 : +S.uf, bSel = S.biome === 'all' ? -1 : +S.biome, g = S.gas;
  const A = new Float64Array((NB + 1) * 12), E = new Float64Array((NB + 1) * 12);
  for (let i = 0; i < N; i++) {
    const m = F.m[i]; if (m < m0 || m > m1) continue;
    if (uSel >= 0 && F.u[i] !== uSel) continue;
    if (!coverPass(F.c[i])) continue;
    const mo = +MONTHS[m].slice(5) - 1, b = F.b[i], e = g === 'total' ? F.co2[i] + F.ch4[i] + F.n2o[i] : F[g][i];
    A[b * 12 + mo] += F.a[i]; E[b * 12 + mo] += e; A[NB * 12 + mo] += F.a[i]; E[NB * 12 + mo] += e;
  }
  const tbl = $('mxSeason'); tbl.textContent = '';
  const hr = tbl.createTHead().insertRow();
  ['Bioma', ...MON, 'Ano todo'].forEach(h => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = h; hr.appendChild(th); });
  const tb = tbl.createTBody(), stops = rampColors(), flip = +css('--ramp-ink-flip');
  const rows = BIOMES.map((n, b) => [n, b]).filter(([, b]) => A.subarray(b * 12, b * 12 + 12).some(v => v > 0));
  // sombreamento por linha: o mês mais alto de cada bioma fica mais escuro (sazonalidade do próprio bioma)
  rows.concat([['Brasil', NB]]).forEach(([n, b]) => {
    const tr = (b === NB ? tbl.createTFoot() : tb).insertRow(); if (b === bSel) tr.className = 'sel';
    const th = document.createElement('th'); th.scope = 'row'; th.textContent = n; tr.appendChild(th);
    const v = MON.map((_, k) => A[b * 12 + k] > 0 ? E[b * 12 + k] / A[b * 12 + k] : null);
    const ok = v.filter(x => x !== null), lo = Math.min(...ok), hi = Math.max(...ok);
    v.forEach((x, k) => {
      const td = tr.insertCell(); td.textContent = x === null ? '-' : nf(1).format(x);
      td.title = MON[k] + ': ' + fmtHa(A[b * 12 + k]).join(' ') + ' queimados';
      if (x !== null && b !== NB && hi > lo) { const c = rampAt(stops, 0.08 + 0.8 * (x - lo) / (hi - lo)); td.style.background = c.color; td.className = 'v';
        if (c.step >= flip) td.style.color = '#fbf8f2'; }
    });
    let sa = 0, se = 0; for (let k = 0; k < 12; k++) { sa += A[b * 12 + k]; se += E[b * 12 + k]; }
    const td = tr.insertCell(); td.className = 'tot'; td.textContent = sa > 0 ? nf(1).format(se / sa) : '-';
  });
  $('sSeason').textContent = 'Σ emissão (' + GAS[g].unit + ') ÷ Σ área queimada (ha), por mês do ano, somando os anos do período'
    + (uSel >= 0 ? ' · ' + DATA.ufs[uSel].sigla : '') + (coverLabel() ? ' · ' + coverLabel() : '')
    + ' · sombreamento por linha: o mês mais escuro é o de maior emissão por hectare naquele bioma';
}

let cExt = null, extVar = 'AREA';
function renderExternal(R) {
  const X = DATA.external; if (!X || !X.rows.length) return;
  $('extCard').hidden = false;
  const vars = [...new Set(X.rows.map(r => r[2]))];
  if (!vars.includes(extVar)) extVar = vars[0];
  const VN = { AREA: 'Área queimada', MS: 'Matéria seca queimada', CO2: 'CO₂', CH4: 'CH₄', N2O: 'N₂O' };
  vars.sort((a, b) => Object.keys(VN).indexOf(a) - Object.keys(VN).indexOf(b));
  const box = $('fExt'); box.textContent = '';
  vars.forEach(v => { const b = document.createElement('button'); b.type = 'button'; b.textContent = VN[v] || v;
    b.setAttribute('aria-pressed', String(v === extVar)); b.addEventListener('click', () => { extVar = v; renderExternal(R); }); box.appendChild(b); });
  const srcs = [...new Set(X.rows.map(r => r[0]))];
  const extYears = new Set(X.rows.map(r => String(r[1])));
  const years = YEARS.filter(y => !(y === LAST.slice(0, 4) && LAST_YEAR_PARTIAL) && extYears.has(y));
  // monitor, Brasil inteiro, sem filtros (para ser comparável)
  const mon = {}, monLo = {}, monHi = {};
  const gi = { CO2: 'co2', CH4: 'ch4', N2O: 'n2o' }[extVar], gw = { CO2: 1, CH4: DATA.method.gwp.CH4, N2O: DATA.method.gwp.N2O }[extVar];
  for (let i = 0; i < N; i++) {
    const y = MONTHS[F.m[i]].slice(0, 4); if (!gi) break;
    const j = { co2: 0, ch4: 1, n2o: 2 }[gi], v = F[gi][i] / gw;
    mon[y] = (mon[y] || 0) + v; monLo[y] = (monLo[y] || 0) + v * ULO[F.c[i]][j]; monHi[y] = (monHi[y] || 0) + v * UHI[F.c[i]][j];
  }
  if (extVar === 'MS') Object.entries(DATA.dm_year).forEach(([y, v]) => { mon[y] = v; });
  if (extVar === 'AREA') for (let i = 0; i < N; i++) { const y = MONTHS[F.m[i]].slice(0, 4); mon[y] = (mon[y] || 0) + F.a[i]; }
  const isA = extVar === 'AREA', fmtX = v => (isA ? fmtHa(v) : fmtT(v)).join(' ');
  const pal = ['--x1', '--x2', '--s7', '--s5'];
  const ds = [{ label: 'Monitor (este painel)', data: years.map(y => mon[y] ?? null),
    err: gi ? years.map(y => mon[y] ? [monLo[y], monHi[y]] : null) : null, ...barStyle(css('--accent')) }]
    .concat(srcs.map((sname, k) => ({ label: sname, data: years.map(y => { const r = X.rows.find(r => r[0] === sname && String(r[1]) === y && r[2] === extVar); return r ? r[3] : null; }),
      ...barStyle(css(pal[k % pal.length])) })));
  if (!cExt) cExt = makeBar($('cExt'), false);
  cExt.data.labels = years; cExt.data.datasets = ds;
  cExt.options.scales.x.stacked = cExt.options.scales.y.stacked = false;
  cExt.options.plugins.tooltip.callbacks.label = c => {
    const m0 = ds[0].data[c.dataIndex], v = c.parsed.y;
    return ' ' + c.dataset.label + ': ' + fmtX(v) + (c.datasetIndex > 0 && m0 && v ? ' (monitor = ' + nf(2).format(m0 / v) + '×)' : '');
  };
  cExt.options.plugins.tooltip.callbacks.afterLabel = c => { const r = ds[c.datasetIndex].err && ds[c.datasetIndex].err[c.dataIndex];
    return r ? ' faixa (95%): ' + fmtX(r[0]) + ' a ' + fmtX(r[1]) : ''; };
  cExt.options.scales.y.ticks.callback = isA ? v => axisTick(v) + ' ha' : axisTick;
  const his = ds.flatMap(d => (d.err || []).filter(Boolean).map(r => r[1]));
  cExt.options.scales.y.suggestedMax = his.length ? Math.max(...his) * 1.1 : undefined;
  themeChart(cExt); cExt.update();
  legend($('lgExt'), ds.map(d => [d.label, d.backgroundColor]));
  $('sExt').textContent = (isA ? 'Área queimada anual no Brasil (ha)' : extVar === 'MS' ? 'Matéria seca queimada no Brasil (t por ano)'
    : 'Emissão anual de ' + VN[extVar] + ' no Brasil, em toneladas do próprio gás (sem GWP)')
    + ' · anos completos com dados nas duas bases' + (gi ? ' · traço: faixa de incerteza do monitor (95%)' : '') + ' · filtros do painel não se aplicam';
  $('extNote').textContent = Object.entries(X.notes || {}).map(([k, v]) => k + ': ' + v).join(' · ')
    + (extVar === 'MS' ? ' · Matéria seca compara a quantidade queimada sem depender dos fatores de emissão.' : '')
    + (isA ? ' · Área: monitor MapBiomas Fogo (30 m) × área queimada do GFED5.1 com pequenos fogos.' : '');
}
function renderMatrices(M) {
  M = M || aggregateYears();
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
    + (S.measure === 'dens' ? 'Por ha de território: Σ emissão (t) ÷ Σ área do território da linha (ha; cobertura: do recorte inteiro). ' : '')
    + (S.measure === 'int' ? 'Por ha queimado: Σ emissão (t) ÷ Σ área queimada (ha) de cada célula. ' : '')
    + 'As matrizes ignoram o filtro de período.';
}

// ---------- tabela ----------
const HEAD = ['Mês', 'Área queimada (ha)', 'CO₂ (t)', 'CH₄ (t CO₂e)', 'N₂O (t CO₂e)', 'CO₂e total (t)', 'CO₂e por ha queimado (t/ha)', 'CO₂e por ha de território (t/ha)'];
let tableRows = [];
function renderTable(R) {
  tableRows = [];
  for (let m = R.m1; m >= R.m0; m--) {
    const a = monthSum(R, m)[0], c2 = R.mG[m * 3], c4 = R.mG[m * 3 + 1], n2 = R.mG[m * 3 + 2], tot = c2 + c4 + n2;
    tableRows.push([MONTHS[m], a, c2, c4, n2, tot, a > 0 ? tot / a : null, R.T > 0 ? tot / R.T : null]);
  }
  const thead = $('tbl').tHead; thead.textContent = '';
  const trh = thead.insertRow();
  HEAD.forEach(h => { const th = document.createElement('th'); th.textContent = h; th.scope = 'col'; trh.appendChild(th); });
  const tb = $('tbl').tBodies[0]; tb.textContent = '';
  tableRows.forEach(r => {
    const tr = tb.insertRow();
    r.forEach((v, j) => { tr.insertCell().textContent = j === 0 ? mLong(v) : v === null ? '—' : nf(j === 6 ? 2 : j === 7 ? 4 : 0).format(v); });
  });
}
$('dlSlice').addEventListener('click', () => {
  const esc = s => /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  const lines = [HEAD.map(esc).join(',')].concat(tableRows.map(r =>
    r.map((v, j) => j === 0 ? v : v === null ? '' : v.toFixed(j >= 6 ? 5 : 1)).join(',')));
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
  tableFrom('mUnc', ['Componente', 'Desvio relativo', 'Referência'], DATA.unc.rows);
  (function () {
    let e = 0, lo = 0, hi = 0;
    for (let i = 0; i < N; i++) { const c = F.c[i], v = [F.co2[i], F.ch4[i], F.n2o[i]];
      v.forEach((x, j) => { e += x; lo += x * ULO[c][j]; hi += x * UHI[c][j]; }); }
    $('mUncTot').textContent = 'Para toda a série (' + mLong(MONTHS[0]) + ' a ' + mLong(LAST) + '), a estimativa central é de '
      + fmtT(e).join(' ') + ' CO₂e, com faixa de 95% entre ' + fmtT(lo).join(' ') + ' e ' + fmtT(hi).join(' ') + '.';
  })();
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
  const M = aggregateYears();
  renderKPIs(R); renderMonthly(R); renderSide(R); renderAnnual(R); renderClass(R); renderUF(R);
  renderScatter(); renderSeasonIntensity(); renderExternal(R); renderMonthMatrix(R); renderMatrices(M); renderTable(R);
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
    ap.add_argument("--external", type=Path, default=EXTERNAL_DEFAULT,
                    help="CSV de comparação externa (comparacao_externa.py); opcional")
    args = ap.parse_args()

    df, from_monthly = load_all(args.data, args.csv)
    if from_monthly:
        df.drop(columns=["ym"]).to_csv(args.csv, index=False, encoding="utf-8")
    payload = build_payload(df, pd.read_csv(args.territory))
    payload["external"] = external_payload(args.external)
    html = (HTML_TEMPLATE
            .replace("__CHART_JS__", args.chart_js.read_text(encoding="utf-8"))
            .replace("__CSV_HREF__", args.csv_href)
            .replace("__CSV_NAME__", Path(args.csv_href).name)
            .replace("__BUILD_DATE__", pd.Timestamp.now().strftime("%d/%m/%Y"))
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))
    for key, svg in method_svgs().items():
        html = html.replace(key, svg)
    args.html.write_text(html, encoding="utf-8")

    print(f"CSV consolidado: {args.csv} ({len(df)} linhas)")
    print(f"Dashboard HTML:  {args.html} ({len(html) // 1024} KB)")
    print(f"Período: {payload['months'][0]} .. {payload['months'][-1]} ({len(payload['months'])} meses)")


if __name__ == "__main__":
    main()
