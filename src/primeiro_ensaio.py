"""
Emissões mensais de fogo por gás (CO2, CH4, N2O) — porta Python de `primeiro_ensaio.js`.
MapBiomas Fogo / IPAM

Gera uma imagem por mês em t/ha com três bandas:
  emiss_CO2       t CO2/ha
  emiss_CO2e_CH4  t CO2e/ha (GWP AR5 = 28)
  emiss_CO2e_N2O  t CO2e/ha (GWP AR5 = 265)

Cadeia por pixel queimado (classe × bioma):
  carbono (t C/ha) = pool do mapa de carbono (classes naturais) ou média fixa (antrópicas)
  carbono queimado = carbono × cf (fator de combustão)
  biomassa seca (t/ha) = carbono queimado ÷ 0,47
  gás (g) = biomassa (kg) × fator de emissão (g/kg) [× GWP para CH4/N2O]

Exporta para `FIRE_EMISS/v00`, sobrescrevendo os assets existentes (`overwrite=True`).

Uso:
  # teste: compara um mês recalculado com o asset atual numa BBox, sem exportar
  ..\\..\\..\\venv\\Scripts\\python.exe primeiro_ensaio.py --test --year 2024 --month 9

  # dry-run: lista as tasks
  ..\\..\\..\\venv\\Scripts\\python.exe primeiro_ensaio.py

  # submete (sobrescreve FIRE_EMISS/v00)
  ..\\..\\..\\venv\\Scripts\\python.exe primeiro_ensaio.py --submit
"""

import argparse
import sys
from pathlib import Path

import ee

_CCAL_DIR = Path(__file__).resolve().parents[2]  # CCAL/
if str(_CCAL_DIR) not in sys.path:
    sys.path.insert(0, str(_CCAL_DIR))

try:
    from BETA_PYTHON import auth
except ImportError:  # pragma: no cover
    auth = None

PROJECT = "mapbiomas-brazil"

CARBON_ASSET = "projects/ee-ipam/assets/SEEG/SEEG14/RETIFICACAO/c_rect_col11_2019"
BURNED_COLLECTION = "projects/mapbiomas-public/assets/brazil/fire/monitor/mapbiomas_fire_monthly_burned_v1"
COVERAGE_ASSET = ("projects/mapbiomas-public/assets/brazil/lulc/collection11/"
                  "mapbiomas_brazil_collection11_coverage_v3")
BIOMAS_ASSET = "projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_biomas_IBGE_2026"
OUTPUT_COLLECTION = "projects/ee-ipam/assets/MAPBIOMAS/FIRE/MONITOR/FIRE_EMISS/v00"
TASK_PREFIX = "WS_IPAM_SEEG-"

LAST_COVERAGE_YEAR = 2025  # anos posteriores usam a cobertura deste ano
SCALE = 30
MAX_PIXELS = 1e13

# Fração de carbono na biomassa seca: biomassa = carbono / 0,47
CARBON_FRACTION = 0.47

# cf: fator de combustão; c_pool: expressão sobre o mapa de carbono (naturais);
# c_mean: carbono médio (t C/ha) usado nas classes antrópicas.
FATORES_POR_BIOMA = {
    "Amazônia": {
        "Agricultura": {"cf": 0.9, "c_pool": "AGB", "c_mean": 9.909136},
        "Pastagem": {"cf": 0.866, "c_pool": "AGB", "c_mean": 9.909136},
        "Formação Campestre": {"cf": 0.866, "c_pool": "AGB+DW+LI", "c_mean": 11.87611},
        "Campo Alagado e Área Pantanosa": {"cf": 0.866, "c_pool": "AGB+DW+LI", "c_mean": 11.87611},
        "Formação Savânica": {"cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 10.5953496},
        "Formação Florestal": {"cf": 0.663, "c_pool": "DW+LI", "c_mean": 14.555805},
    },
    "Cerrado": {
        "Agricultura": {"cf": 0.9, "c_pool": "AGB", "c_mean": 9.444437},
        "Pastagem": {"cf": 0.607, "c_pool": "AGB", "c_mean": 9.444437},
        "Formação Campestre": {"cf": 0.607, "c_pool": "AGB+DW+LI", "c_mean": 11.814823},
        "Campo Alagado e Área Pantanosa": {"cf": 0.607, "c_pool": "AGB+DW+LI", "c_mean": 11.814823},
        "Formação Savânica": {"cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 27.405347},
        "Formação Florestal": {"cf": 0.656, "c_pool": "DW+LI", "c_mean": 12.530418},
    },
    "Mata Atlântica": {
        "Agricultura": {"cf": 0.9, "c_pool": "AGB", "c_mean": 7.960108},
        "Pastagem": {"cf": 0.769, "c_pool": "AGB", "c_mean": 7.960108},
        "Formação Campestre": {"cf": 0.769, "c_pool": "AGB+DW+LI", "c_mean": 25.037944},
        "Campo Alagado e Área Pantanosa": {"cf": 0.769, "c_pool": "AGB+DW+LI", "c_mean": 25.037944},
        "Formação Savânica": {"cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 8.0815222},
        "Formação Florestal": {"cf": 0.663, "c_pool": "DW+LI", "c_mean": 11.409046},
    },
    "Pantanal": {
        "Agricultura": {"cf": 0.9, "c_pool": "AGB", "c_mean": 9.938581},
        "Pastagem": {"cf": 0.6925, "c_pool": "AGB", "c_mean": 9.938581},
        "Formação Campestre": {"cf": 0.6925, "c_pool": "AGB+DW+LI", "c_mean": 12.371491},
        "Campo Alagado e Área Pantanosa": {"cf": 0.6925, "c_pool": "AGB+DW+LI", "c_mean": 12.371491},
        "Formação Savânica": {"cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 12.6971932},
        "Formação Florestal": {"cf": 0.656, "c_pool": "DW+LI", "c_mean": 16.180421},
    },
    "Caatinga": {
        "Agricultura": {"cf": 0.9, "c_pool": "AGB", "c_mean": 9.049347},
        "Pastagem": {"cf": 0.649, "c_pool": "AGB", "c_mean": 9.049347},
        "Formação Campestre": {"cf": 0.649, "c_pool": "AGB+DW+LI", "c_mean": 11.561256},
        "Campo Alagado e Área Pantanosa": {"cf": 0.649, "c_pool": "AGB+DW+LI", "c_mean": 11.561256},
        "Formação Savânica": {"cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 7.9012824},
        "Formação Florestal": {"cf": 0.85075, "c_pool": "DW+LI", "c_mean": 10.723852},
    },
    "Pampa": {
        "Agricultura": {"cf": 0.9, "c_pool": "AGB", "c_mean": 11.1815},
        "Pastagem": {"cf": 0.944, "c_pool": "AGB", "c_mean": 11.1815},
        "Formação Campestre": {"cf": 0.944, "c_pool": "AGB+DW+LI", "c_mean": 15.788241},
        "Campo Alagado e Área Pantanosa": {"cf": 0.944, "c_pool": "AGB+DW+LI", "c_mean": 15.788241},
        "Formação Savânica": {"cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 0},
        "Formação Florestal": {"cf": 0.656, "c_pool": "DW+LI", "c_mean": 4.606741},
    },
}

# Fatores de emissão (g/kg de matéria seca); agricultura N2O: IPCC Tabela 2.5
FATORES_POR_GAS = {
    "CO2": {"Formação Florestal": 1580, "Formação Savânica": 1613, "Formação Campestre": 1613,
            "Campo Alagado e Área Pantanosa": 1613, "Pastagem": 1613, "Agricultura": 1515},
    "CH4": {"Formação Florestal": 6.8, "Formação Savânica": 2.3, "Formação Campestre": 2.3,
            "Campo Alagado e Área Pantanosa": 2.3, "Pastagem": 2.3, "Agricultura": 2.7},
    "N2O": {"Formação Florestal": 0.2, "Formação Savânica": 0.2, "Formação Campestre": 0.2,
            "Campo Alagado e Área Pantanosa": 0.2, "Pastagem": 0.2, "Agricultura": 0.07},
}

GWP_AR5 = {"CH4": 28, "N2O": 265}
GASES = ["CO2", "CH4", "N2O"]
BAND_NAMES = {"CO2": "emiss_CO2", "CH4": "emiss_CO2e_CH4", "N2O": "emiss_CO2e_N2O"}

CLASSES = {
    "Formação Florestal": [3, 6, 5, 49, 9],
    "Formação Savânica": [4, 77, 50],
    "Formação Campestre": [12, 7],
    "Campo Alagado e Área Pantanosa": [11],
    "Pastagem": [15, 21],
    "Agricultura": [39, 20, 40, 62, 41, 46, 47, 35, 48],
}
ANTROPICAS = {"Pastagem", "Agricultura"}


def connect(project, account_profile=None):
    if account_profile:
        if auth is None:
            raise RuntimeError("BETA_PYTHON.auth não encontrado; não dá para usar --account-profile")
        ee.Initialize(credentials=auth.load(account_profile), project=project)
    else:
        ee.Initialize(project=project)


def gas_factor_t_ha(carbon_t_ha, coverage_str, gas):
    """Fator que leva carbono queimado (t C/ha) a t/ha do gás (CO2e para CH4/N2O).

    t C/ha ÷ 0,47 = t MS/ha; × EF (g/kg = kg/t) = kg gás/ha; ÷ 1000 = t gás/ha.
    Equivale ao JS (kg → g → ÷1e6), sem multiplicar e dividir pela área do pixel.
    """
    factor = FATORES_POR_GAS[gas][coverage_str] / 1000.0
    if gas in GWP_AR5:
        factor *= GWP_AR5[gas]
    return carbon_t_ha.divide(CARBON_FRACTION).multiply(factor)


def build_month(burned, year, carbon, coverage, biomas):
    cov_year = min(year, LAST_COVERAGE_YEAR)
    coverage_year = coverage.select(f"classification_{cov_year}")
    recipes = {gas: ee.Image(0) for gas in GASES}

    for bioma_str, coberturas in FATORES_POR_BIOMA.items():
        bioma_mask = ee.Image().paint(biomas.filter(ee.Filter.eq("Bioma", bioma_str))).eq(0)
        for coverage_str, obj in coberturas.items():
            coverage_binary = coverage_year.eq(CLASSES[coverage_str]).reduce("max")

            if coverage_str in ANTROPICAS:
                pools = (ee.Image(obj["c_mean"]).rename("AGB")
                         .addBands(ee.Image(0).rename("CDW"))
                         .addBands(ee.Image(0).rename("LITTER")))
            else:
                pools = carbon

            burned_carbon = pools.expression(obj["c_pool"], {
                "AGB": pools.select("AGB"),
                "DW": pools.select("CDW"),
                "LI": pools.select("LITTER"),
            }).multiply(obj["cf"])

            where_mask = coverage_binary.And(burned).And(bioma_mask)
            for gas in GASES:
                value = gas_factor_t_ha(burned_carbon, coverage_str, gas).float()
                recipes[gas] = recipes[gas].where(where_mask, value)

    return ee.Image.cat([recipes[g].rename(BAND_NAMES[g]) for g in GASES])


def month_props(name):
    _, y, m = name.split("-")
    year, month = int(y), int(m)
    description = f"co2_fire_emiss_{year}_{month:02d}"
    ym = f"{year}_{month:02d}"
    start = ee.Date.fromYMD(year, month, 1)
    return year, month, description, {
        "metric": "CO2 equivalent",
        "biomass_from_carbon": "carbon / 0.47",
        "unit": "t/ha",
        "month": f"{month:02d}",
        "year_month": ym,
        "name": description,
        "system:time_start": start.millis(),
        "system:time_end": start.advance(1, "month").millis(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--submit", action="store_true",
                        help="submete as tasks (sobrescreve FIRE_EMISS/v00); sem isto é dry-run")
    parser.add_argument("--test", action="store_true",
                        help="compara um mês recalculado com o asset atual numa BBox; não exporta")
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--account-profile", default="workspace2")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                        default=(-47.0, -15.0, -46.0, -14.0))
    parser.add_argument("--scale", type=int, default=None, help="padrão 30 (teste: 30)")
    args = parser.parse_args()

    connect(args.project, args.account_profile)

    carbon = ee.Image(CARBON_ASSET)
    burned_col = ee.ImageCollection(BURNED_COLLECTION)
    coverage = ee.Image(COVERAGE_ASSET)
    biomas = ee.FeatureCollection(BIOMAS_ASSET)
    region = biomas.geometry().bounds()

    names = burned_col.aggregate_array("name").getInfo()
    months = sorted((month_props(n)[0], month_props(n)[1], n) for n in names)
    if args.year is not None:
        months = [m for m in months if m[0] == args.year]
    if args.month is not None:
        months = [m for m in months if m[1] == args.month]
    if not months:
        print("Nenhum mês corresponde aos filtros.")
        return 1
    print(f"Meses: {len(months)} ({months[0][2]} .. {months[-1][2]})")

    if args.test:
        year, month, name = months[-1]
        _, _, description, _ = month_props(name)
        scale = args.scale or 30
        geom = ee.Geometry.BBox(*args.bounds)
        burned = burned_col.filter(ee.Filter.eq("name", name)).first()
        new = build_month(burned, year, carbon, coverage, biomas)
        old = ee.Image(f"{OUTPUT_COLLECTION}/{description}")
        area = ee.Image.pixelArea().divide(10000)
        stats = (new.multiply(area).rename([b + "_new" for b in BAND_NAMES.values()])
                 .addBands(old.select(list(BAND_NAMES.values())).multiply(area)
                           .rename([b + "_old" for b in BAND_NAMES.values()]))
                 .reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e12).getInfo())
        print(f"Teste {description} | BBox {args.bounds} | escala {scale} m (t no recorte)")
        expected = 1 / CARBON_FRACTION ** 2
        for b in BAND_NAMES.values():
            n, o = stats[b + "_new"], stats[b + "_old"]
            ratio = n / o if o else float("nan")
            print(f"  {b:16s} novo {n:14.2f}  atual {o:14.2f}  razão {ratio:.5f} "
                  f"(esperado se o asset atual usa ×0,47: {expected:.5f})")
        return 0

    tasks = []
    for year, month, name in months:
        _, _, description, _ = month_props(name)
        tasks.append((year, month, name, description))
    print(f"\n{len(tasks)} task(s) -> {OUTPUT_COLLECTION} (overwrite=True)")
    for *_, description in tasks[:3]:
        print(f"  {TASK_PREFIX}{description}")
    if len(tasks) > 3:
        print("  ...")

    if not args.submit:
        print("\n[DRY-RUN] Nada foi submetido. Use --submit para enviar.")
        return 0

    for year, month, name, description in tasks:
        burned = burned_col.filter(ee.Filter.eq("name", name)).first()
        _, _, _, props = month_props(name)
        img = ee.Image(build_month(burned, year, carbon, coverage, biomas)
                       .copyProperties(burned)).set(props)
        task = ee.batch.Export.image.toAsset(
            image=img,
            description=TASK_PREFIX + description,
            assetId=f"{OUTPUT_COLLECTION}/{description}",
            pyramidingPolicy={".default": "median"},
            region=region,
            scale=SCALE,
            maxPixels=MAX_PIXELS,
            overwrite=True,
        )
        task.start()
        print(f"  submetida: {TASK_PREFIX}{description} (id={task.id})")
    print(f"\n{len(tasks)} task(s) submetida(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
