"""Comparação externa do monitor de emissões: GFED5.1 e CAMS GFAS, totais anuais do Brasil.

Saída: externo/comparacao_anual.csv (fonte, ano, variavel, valor_t, escopo), lida por
construir_dashboard.py. Variáveis em toneladas do próprio gás (sem GWP): CO2, CH4, N2O e MS
(matéria seca queimada, quando a base fornece); AREA (área queimada) vem em hectares.

Etapas (cada uma pode ser rodada sozinha):

  python comparacao_externa.py mascara            # fração de cada célula 0,25° e 0,1° dentro do Brasil (GEE)
  python comparacao_externa.py gfed               # baixa GFED5.1 mensal (Zenodo, 1,7 GB) e soma 2019-2022
  python comparacao_externa.py gfed --nrt-dir D   # + anos NRT (2023+) baixados à parte via SFTP do GFED
  python comparacao_externa.py gfas               # CAMS GFAS via API do ADS (requer ~/.cdsapirc)
  python comparacao_externa.py seeg               # SEEG 14, fogo em vegetação nativa (CSVs do Drive, workspace2)

Requer: numpy, pandas, netCDF4 (pip install netCDF4); earthengine-api para a máscara; cdsapi para GFAS.
"""
import argparse
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / ("../data/externo" if HERE.name == "src" else "externo")
OUT_CSV = OUT_DIR / "comparacao_anual.csv"
CACHE = OUT_DIR / "cache"
YEARS = range(2019, 2026)

# Brasil: caixa envolvente em graus (oeste, sul, leste, norte), alinhada às grades de 0,25° e 0,1°
BBOX = (-74.0, -34.0, -34.0, 6.0)
BIOMAS = "projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_biomas_IBGE_2026"

GFED_ZIP_URL = "https://zenodo.org/records/16794692/files/GFED5.1_monthly.zip?download=1"
GFED_ECO_URL = "https://zenodo.org/records/16794692/files/GFED5.1_ecosystem.zip?download=1"  # área queimada
GFED_SCOPE = ("GFED5.1: área queimada MODIS com pequenos fogos, todos os fogos de paisagem "
              "(inclui desmatamento e turfa), 0,25°")
GFAS_SCOPE = "CAMS GFAS v1.2: potência radiativa do fogo (MODIS), todos os fogos, 0,1°"
GAS_GFED = {"CO2": "CO2", "CH4": "CH4", "N2O": "N2O", "MS": "DM"}


# ---------------------------------------------------------------- máscara do Brasil
def mask_path(res):
    return CACHE / f"mascara_brasil_{str(res).replace('.', 'p')}.npy"


def build_mask(res):
    """Fração de cada célula (res graus) dentro dos limites de biomas do IBGE, calculada no GEE."""
    ccal = HERE.parents[1] if HERE.name != "src" else HERE.parent
    sys.path.insert(0, str(ccal))
    import ee
    try:
        from BETA_PYTHON import auth
        ee.Initialize(credentials=auth.load("workspace2"), project="mapbiomas-brazil")
    except ImportError:
        ee.Initialize(project="mapbiomas-brazil")
    from matplotlib.path import Path as MPath
    w, s, e, n = BBOX
    nx, ny = round((e - w) / res), round((n - s) / res)
    CACHE.mkdir(parents=True, exist_ok=True)
    gj = CACHE / "brasil_simplificado.json"
    if gj.exists():
        geom = pd.read_json(gj, typ="series").to_dict()
    else:
        # contorno do Brasil (união dos biomas IBGE) simplificado a ~1 km
        geom = ee.FeatureCollection(BIOMAS).geometry(maxError=1000).simplify(maxError=1000).getInfo()
        pd.Series(geom).to_json(gj)
    def polygons(g):
        if g["type"] == "Polygon":
            return [g["coordinates"]]
        if g["type"] == "MultiPolygon":
            return g["coordinates"]
        if g["type"] == "GeometryCollection":
            return [p for sub in g["geometries"] for p in polygons(sub)]
        return []  # pontos e linhas soltos da simplificação
    polys = polygons(geom)
    # fração da célula = proporção de subpontos (sub × sub por célula) dentro do contorno
    sub = max(4, round(0.025 / res * 10))  # subpontos a cada ~2,5 km
    step = res / sub
    xs = w + (np.arange(nx * sub) + 0.5) * step
    ys = n - (np.arange(ny * sub) + 0.5) * step
    inside = np.zeros((ny * sub, nx * sub), dtype=bool)
    for poly in polys:
        ring = np.asarray(poly[0])
        if len(ring) < 4:
            continue
        # só os subpontos dentro da caixa do polígono
        c0, c1 = np.searchsorted(xs, ring[:, 0].min()), np.searchsorted(xs, ring[:, 0].max())
        r0, r1 = np.searchsorted(-ys, -ring[:, 1].max()), np.searchsorted(-ys, -ring[:, 1].min())
        if c1 <= c0 or r1 <= r0:
            continue
        X, Y = np.meshgrid(xs[c0:c1], ys[r0:r1])
        pts = np.column_stack([X.ravel(), Y.ravel()])
        hit = MPath(ring).contains_points(pts)
        for hole in poly[1:]:
            hit &= ~MPath(np.asarray(hole)).contains_points(pts)
        inside[r0:r1, c0:c1] |= hit.reshape(r1 - r0, c1 - c0)
    arr = inside.reshape(ny, sub, nx, sub).mean(axis=(1, 3))
    np.save(mask_path(res), arr)
    print(f"máscara {res}°: {arr.shape}, células com Brasil: {(arr > 0).sum()}, soma = {arr.sum():.0f}")
    return arr


def load_mask(res):
    p = mask_path(res)
    if not p.exists():
        raise SystemExit(f"máscara ausente ({p}); rode antes: python {Path(__file__).name} mascara")
    return np.load(p)


def window(lat, lon, res):
    """Índices da caixa do Brasil numa grade global (lat/lon de centros de célula)."""
    w, s, e, n = BBOX
    iy = np.where((lat > s) & (lat < n))[0]
    ix = np.where((lon > w) & (lon < e))[0]
    # a máscara vai de norte para sul
    flip = lat[iy[0]] < lat[iy[-1]]
    return iy, ix, flip


# ---------------------------------------------------------------- GFED5.1
def gfed_sum_file(path, mask):
    import netCDF4 as nc
    out = {}
    with nc.Dataset(path) as ds:
        lat, lon = ds["lat"][:], ds["lon"][:]
        iy, ix, flip = window(np.asarray(lat), np.asarray(lon), 0.25)
        for var, name in GAS_GFED.items():
            if name not in ds.variables:
                continue
            g = np.asarray(ds[name][:, iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1], dtype=float)  # g por mês por célula
            if flip:
                g = g[:, ::-1, :]
            if g.shape[1:] != mask.shape:
                raise SystemExit(f"{path.name}: grade {g.shape[1:]} ≠ máscara {mask.shape}")
            out[var] = float(np.nansum(g * mask[None]) / 1e6)  # g → t
    return out


def run_gfed(args):
    mask = load_mask(0.25)
    CACHE.mkdir(parents=True, exist_ok=True)
    zpath = Path(args.zip) if args.zip else CACHE / "GFED5.1_monthly.zip"
    if not zpath.exists():
        import urllib.request
        print(f"baixando {GFED_ZIP_URL} → {zpath} (≈1,7 GB)")
        urllib.request.urlretrieve(GFED_ZIP_URL, zpath)
    rows = []
    with zipfile.ZipFile(zpath) as z:
        for y in YEARS:
            names = [m for m in z.namelist() if m.endswith(f"_{y}.nc") and "__MACOSX" not in m]
            if not names:
                continue
            target = CACHE / Path(names[0]).name
            if not target.exists():
                with z.open(names[0]) as src, open(target, "wb") as dst:
                    dst.write(src.read())
            for var, v in gfed_sum_file(target, mask).items():
                rows.append(["GFED5.1", y, var, v, GFED_SCOPE])
            print("GFED", y, "ok")
    if args.nrt_dir:
        for f in sorted(Path(args.nrt_dir).glob("*.nc")):
            y = int(f.stem[-4:])
            if y in YEARS and not any(r[1] == y for r in rows):
                for var, v in gfed_sum_file(f, mask).items():
                    rows.append(["GFED5.1", y, var, v, GFED_SCOPE + " (NRT)"])
                print("GFED NRT", y, "ok")
    # área queimada (ha), do arquivo de ecossistemas (304 MB)
    eco = CACHE / "GFED5.1_ecosystem.zip"
    if not eco.exists() and not args.sem_area:
        import urllib.request
        print(f"baixando {GFED_ECO_URL} → {eco} (≈300 MB)")
        urllib.request.urlretrieve(GFED_ECO_URL, eco)
    if eco.exists():
        import netCDF4 as nc
        with zipfile.ZipFile(eco) as z:
            for y in YEARS:
                names = [m for m in z.namelist() if m.endswith(f"_ecosystem_{y}.nc") and "__MACOSX" not in m]
                if not names:
                    continue
                target = CACHE / Path(names[0]).name
                if not target.exists():
                    with z.open(names[0]) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                with nc.Dataset(target) as ds:
                    iy, ix, flip = window(np.asarray(ds["lat"][:]), np.asarray(ds["lon"][:]), 0.25)
                    ba = np.asarray(ds["burned_area"][:, iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1], dtype=float)  # m² por mês
                    if flip:
                        ba = ba[:, ::-1, :]
                    rows.append(["GFED5.1", y, "AREA", float(np.nansum(ba * mask[None]) / 1e4), GFED_SCOPE])
    write_rows("GFED5.1", rows)


# ---------------------------------------------------------------- CAMS GFAS
def run_gfas(args):
    try:
        import cdsapi
    except ImportError:
        raise SystemExit("instale cdsapi (pip install cdsapi) e configure ~/.cdsapirc com a chave do ADS")
    import netCDF4 as nc
    mask = load_mask(0.1)
    CACHE.mkdir(parents=True, exist_ok=True)
    c = cdsapi.Client()
    w, s, e, n = BBOX
    rows = []
    for y in YEARS:
        f = CACHE / f"gfas_{y}.nc"
        if not f.exists():
            c.retrieve("cams-global-fire-emissions-gfas", {
                "variable": ["wildfire_flux_of_carbon_dioxide", "wildfire_flux_of_methane",
                             "wildfire_flux_of_nitrous_oxide", "wildfire_combustion_rate"],
                "date": f"{y}-01-01/{y}-12-31", "area": [n, w, s, e], "data_format": "netcdf"}, str(f))
        with nc.Dataset(f) as ds:
            lat = np.asarray(ds["latitude"][:]); lon = np.asarray(ds["longitude"][:])
            area = cell_area_m2(lat, 0.1)[:, None]
            sub = mask[: len(lat), : len(lon)]
            for var, name in {"CO2": "co2fire", "CH4": "ch4fire", "N2O": "n2ofire", "MS": "crfire"}.items():
                if name not in ds.variables:
                    continue
                flux = np.asarray(ds[name][:], dtype=float)  # kg m-2 s-1, diário
                tot = np.nansum(flux * area[None] * sub[None]) * 86400 / 1000  # kg → t
                rows.append(["CAMS GFAS", y, var, float(tot), GFAS_SCOPE])
        print("GFAS", y, "ok")
    write_rows("CAMS GFAS", rows)


def cell_area_m2(lat, res):
    r = 6371007.2
    rad = np.deg2rad
    return (r ** 2) * rad(res) * (np.sin(rad(lat + res / 2)) - np.sin(rad(lat - res / 2)))


# ---------------------------------------------------------------- SEEG 14 (fogo em vegetação nativa)
SEEG_FOLDER = "1xRnvyz40d74JvRGhpXsWzrtlZ1V5WhSG"  # Drive: SEEG14_YEARLY-2 (seeg14_emissions_AAAA.csv)
SEEG_SCOPE = ("SEEG 14: queimadas não associadas ao desmatamento, só vegetação nativa (floresta, savana, campo); "
              "CH₄ e N₂O da combustão imediata; CO₂ = balanço da mortalidade tardia na floresta + savana (campo sem CO₂)")


def run_seeg(args):
    """Soma por ano os CSVs do SEEG 14 (município × bioma × área protegida) baixados do Drive."""
    import requests
    ccal = HERE.parents[1] if HERE.name != "src" else HERE.parent
    sys.path.insert(0, str(ccal))
    from BETA_PYTHON import auth
    from google.auth.transport.requests import Request
    cred = auth.load("workspace2"); cred.refresh(Request())
    hdr = {"Authorization": f"Bearer {cred.token}"}
    r = requests.get("https://www.googleapis.com/drive/v3/files", headers=hdr, timeout=60, params={
        "q": f"'{args.folder}' in parents and trashed=false", "fields": "files(id,name)", "pageSize": 500})
    r.raise_for_status()
    ids = {f["name"]: f["id"] for f in r.json()["files"]}
    cache = CACHE / "seeg14"; cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in YEARS:
        name = f"seeg14_emissions_{y}.csv"
        if name not in ids:
            continue
        f = cache / name
        if not f.exists():
            f.write_bytes(requests.get(f"https://www.googleapis.com/drive/v3/files/{ids[name]}", params={"alt": "media"},
                                       headers=hdr, timeout=300).content)
        t = pd.read_csv(f).sum(numeric_only=True)
        for var, cols in {"CO2": ["CO2_floresta_Mg", "CO2_savana_Mg"],
                          "CH4": ["CH4_campo_Mg", "CH4_floresta_Mg", "CH4_savana_Mg"],
                          "N2O": ["N2O_campo_Mg", "N2O_floresta_Mg", "N2O_savana_Mg"]}.items():
            rows.append(["SEEG 14", y, var, float(sum(t[c] for c in cols)), SEEG_SCOPE, "nativa"])  # Mg = t
        print("SEEG", y, "ok")
    write_rows("SEEG 14", rows)


# ---------------------------------------------------------------- saída
def write_rows(source, rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [r if len(r) == 6 else r + ["todas"] for r in rows]  # escopo do monitor comparável: todas | nativa
    new = pd.DataFrame(rows, columns=["fonte", "ano", "variavel", "valor_t", "escopo", "escopo_monitor"])
    if OUT_CSV.exists():
        old = pd.read_csv(OUT_CSV)
        if "escopo_monitor" not in old.columns:
            old["escopo_monitor"] = "todas"
        new = pd.concat([old[old["fonte"] != source], new], ignore_index=True)
    new.sort_values(["fonte", "variavel", "ano"]).to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"{OUT_CSV}: {len(new)} linhas")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mascara")
    g = sub.add_parser("gfed"); g.add_argument("--zip"); g.add_argument("--nrt-dir")
    g.add_argument("--sem-area", action="store_true", help="não baixa o arquivo de ecossistemas (área queimada)")
    sub.add_parser("gfas")
    sg = sub.add_parser("seeg"); sg.add_argument("--folder", default=SEEG_FOLDER, help="id da pasta do Drive com seeg14_emissions_AAAA.csv")
    args = ap.parse_args()
    if args.cmd == "mascara":
        build_mask(0.25); build_mask(0.1)
    elif args.cmd == "gfed":
        run_gfed(args)
    elif args.cmd == "seeg":
        run_seeg(args)
    else:
        run_gfas(args)


if __name__ == "__main__":
    main()
