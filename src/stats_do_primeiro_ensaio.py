"""
Estatísticas de emissões por gás (CO2, CH4, N2O) e uso/cobertura por Bioma × UF (IBGE)
MapBiomas Fogo / IPAM

Pipeline Python (Earth Engine), com export **por mês** (um CSV por `year_month`)
e estatísticas cruzadas por bioma × UF × classe.

Entrada: `FIRE_EMISS/v00` com três bandas em t/ha, geradas por `primeiro_ensaio.js`:
  emiss_CO2 (t CO2), emiss_CO2e_CH4 e emiss_CO2e_N2O (t CO2e, GWP AR5: 28 e 265).
Área e os três gases são somados numa única redução agrupada; o CO2e total é
CO2 + CH4 + N2O (em CO2e). A versão anterior, de uma banda (carbono queimado,
rotulado "Emissão CO2"), está em `reference/stats_do_primeiro_ensaio_uma_banda.py`.

As legendas vieram de `users/geomapeamentoipam/MapBiomas__Fogo:00_Tools/Legends.js`
(a API Python não suporta `require`), embutidas abaixo.

Uso:
  # teste rápido: 1 mês, região pequena, escala grosseira, sem exportar
  ..\\..\\..\\venv\\Scripts\\python.exe stats_do_primeiro_ensaio.py --test

  # dry-run: lista as tasks por mês sem submeter nada
  ..\\..\\..\\venv\\Scripts\\python.exe stats_do_primeiro_ensaio.py

  # submete um CSV por mês pro Drive (pasta monitoramento-sentinel; Bioma × UF)
  ..\\..\\..\\venv\\Scripts\\python.exe stats_do_primeiro_ensaio.py --submit

  # filtros de ano/mês (valem para teste e para o export)
  ..\\..\\..\\venv\\Scripts\\python.exe stats_do_primeiro_ensaio.py --year 2025 --month 9 --submit
"""

import argparse
import sys
from pathlib import Path

import ee

# Permite importar BETA_PYTHON.auth (perfil isolado de credencial, ex.: workspace2)
_CCAL_DIR = Path(__file__).resolve().parents[2]  # CCAL/
if str(_CCAL_DIR) not in sys.path:
    sys.path.insert(0, str(_CCAL_DIR))

try:
    from BETA_PYTHON import auth
except ImportError:  # pragma: no cover
    auth = None

PROJECT = "mapbiomas-brazil"

VERSAO = "_2026"
DESCRIPTION = "csv-monitor-mensal-emissoes-gases-v2-bioma-uf_col11" + VERSAO  # v2: biomassa = C / 0,47
DRIVER_FOLDER = "monitoramento-sentinel"
TASK_PREFIX = "WS_IPAM_MNEMISSOES-"

SCALE = 30
MAX_PIXELS = 1e12

EMISS_COLLECTION = "projects/ee-ipam/assets/MAPBIOMAS/FIRE/MONITOR/FIRE_EMISS/v00"

# banda do asset -> coluna do CSV (valores em t por pixel após multiplicar pela área)
GAS_BANDS = ["emiss_CO2", "emiss_CO2e_CH4", "emiss_CO2e_N2O"]
GAS_COLUMNS = {
    "emiss_CO2": "Emissão CO2 (t)",
    "emiss_CO2e_CH4": "Emissão CH4 (t CO2e)",
    "emiss_CO2e_N2O": "Emissão N2O (t CO2e)",
}
TOTAL_COLUMN = "Emissão CO2e total (t)"

EXPORT_SELECTORS = [
    "Ano", "id", "bioma_id", "Bioma", "uf_id", "UF", "SIGLA_UF", "class_int",
    "Níveis", "Nível 0", "Nível 1", "Nível 1_1", "Nível 2", "Nível 3", "Nível 4",
    "Área ha", "Área km²", *GAS_COLUMNS.values(), TOTAL_COLUMN,
    "Situação", "Mês", "mes",
]

# ---------------------------------------------------------------------------
# Legendas (dados puros; viram ee.Dictionary em `connect`, após ee.Initialize)
# ---------------------------------------------------------------------------
_BIOMAS_LEGEND = {
    "1": "Amazônia",
    "2": "Caatinga",
    "3": "Cerrado",
    "4": "Mata Atlântica",
    "5": "Pampa",
    "6": "Pantanal",
}

# Códigos IBGE do asset limite_ufs_IBGE_2025 (CD_UF).
_UFS_LEGEND = {
    11: ("Rondônia", "RO"), 12: ("Acre", "AC"), 13: ("Amazonas", "AM"),
    14: ("Roraima", "RR"), 15: ("Pará", "PA"), 16: ("Amapá", "AP"),
    17: ("Tocantins", "TO"), 21: ("Maranhão", "MA"), 22: ("Piauí", "PI"),
    23: ("Ceará", "CE"), 24: ("Rio Grande do Norte", "RN"),
    25: ("Paraíba", "PB"), 26: ("Pernambuco", "PE"), 27: ("Alagoas", "AL"),
    28: ("Sergipe", "SE"), 29: ("Bahia", "BA"), 31: ("Minas Gerais", "MG"),
    32: ("Espírito Santo", "ES"), 33: ("Rio de Janeiro", "RJ"),
    35: ("São Paulo", "SP"), 41: ("Paraná", "PR"), 42: ("Santa Catarina", "SC"),
    43: ("Rio Grande do Sul", "RS"), 50: ("Mato Grosso do Sul", "MS"),
    51: ("Mato Grosso", "MT"), 52: ("Goiás", "GO"), 53: ("Distrito Federal", "DF"),
}
_UF_NAMES = {str(code): value[0] for code, value in _UFS_LEGEND.items()}
_UF_SIGLAS = {str(code): value[1] for code, value in _UFS_LEGEND.items()}

_FOGO_SITUATION_MONTH = {
    0: "Não Fogo",
    1: "Fogo", 2: "Fogo", 3: "Fogo", 4: "Fogo", 5: "Fogo", 6: "Fogo",
    7: "Fogo", 8: "Fogo", 9: "Fogo", 10: "Fogo", 11: "Fogo", 12: "Fogo",
}

_FOGO_MONTHS_STR = {
    0: "Não Fogo",
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio",
    6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro",
    11: "Novembro", 12: "Dezembro",
}

_FOGO_MONTHS_INT = {
    0: "Não Fogo",
    1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
    7: 7, 8: 8, 9: 9, 10: 10, 11: 11, 12: 12,
}

_LULC_NIVEIS = {
    0: "Não observado",
    1: "Nível 1",
    3: "Nível 2", 4: "Nível 2", 5: "Nível 2", 6: "Nível 2", 7: "Nível 2",
    49: "Nível 2",
    10: "Nível 1",
    11: "Nível 2", 12: "Nível 2", 77: "Nível 2", 32: "Nível 2",
    29: "Nível 2", 50: "Nível 2", 13: "Nível 2", 84: "Nível 2",
    14: "Nível 1",
    15: "Nível 2", 18: "Nível 2",
    19: "Nível 3",
    39: "Nível 4", 20: "Nível 4", 40: "Nível 4", 62: "Nível 4", 41: "Nível 4",
    36: "Nível 3",
    46: "Nível 4", 47: "Nível 4", 35: "Nível 4", 48: "Nível 4",
    9: "Nível 2", 21: "Nível 2",
    22: "Nível 1",
    23: "Nível 2", 24: "Nível 2", 30: "Nível 2", 75: "Nível 2",
    91: "Nível 2", 25: "Nível 2",
    26: "Nível 1",
    33: "Nível 2", 31: "Nível 3",
    27: "Não observado",
}

_LULC_NIVEL_0 = {
    0: "Não observado",
    1: "Natural", 3: "Natural", 4: "Natural", 5: "Natural", 6: "Natural",
    7: "Natural", 49: "Natural",
    10: "Natural", 11: "Natural", 12: "Natural", 77: "Natural", 32: "Natural",
    29: "Antrópico",
    50: "Natural", 13: "Natural", 84: "Natural",
    14: "Antrópico", 15: "Antrópico", 18: "Antrópico", 19: "Antrópico",
    39: "Antrópico", 20: "Antrópico", 40: "Antrópico", 62: "Antrópico",
    41: "Antrópico", 36: "Antrópico", 46: "Antrópico", 47: "Antrópico",
    35: "Antrópico", 48: "Antrópico", 9: "Antrópico", 21: "Antrópico",
    22: "Antrópico", 23: "Antrópico", 24: "Antrópico", 30: "Antrópico",
    75: "Antrópico", 91: "Antrópico", 25: "Antrópico", 26: "Antrópico",
    33: "Antrópico", 31: "Antrópico",
    27: "Não observado",
}

_LULC_NIVEL_1 = {
    0: "Não observado",
    1: "Floresta", 3: "Floresta", 4: "Floresta", 5: "Floresta", 6: "Floresta",
    7: "Floresta", 49: "Floresta",
    10: "Vegetação Herbácea e Arbustiva", 11: "Vegetação Herbácea e Arbustiva",
    12: "Vegetação Herbácea e Arbustiva", 77: "Vegetação Herbácea e Arbustiva",
    32: "Vegetação Herbácea e Arbustiva",
    29: "Área não vegetada",
    50: "Vegetação Herbácea e Arbustiva", 13: "Vegetação Herbácea e Arbustiva",
    84: "Vegetação Herbácea e Arbustiva",
    14: "Agropecuária", 15: "Agropecuária", 18: "Agropecuária",
    19: "Agropecuária", 39: "Agropecuária", 20: "Agropecuária",
    40: "Agropecuária", 62: "Agropecuária", 41: "Agropecuária",
    36: "Agropecuária", 46: "Agropecuária", 47: "Agropecuária",
    35: "Agropecuária", 48: "Agropecuária", 9: "Agropecuária",
    21: "Agropecuária",
    22: "Área não vegetada", 23: "Área não vegetada", 24: "Área não vegetada",
    30: "Área não vegetada", 75: "Área não vegetada", 91: "Área não vegetada",
    25: "Área não vegetada",
    26: "Corpos D´água", 33: "Corpos D´água", 31: "Corpos D´água",
    27: "Não observado",
}

_LULC_NIVEL_1_1 = {
    0: "Não observado",
    1: "Formação Florestal", 3: "Formação Florestal", 5: "Formação Florestal",
    6: "Formação Florestal", 7: "Formação Florestal",
    4: "Formação Savânica", 49: "Formação Savânica",
    10: "Formação Campestre", 12: "Formação Campestre",
    77: "Formação Campestre", 32: "Formação Campestre",
    50: "Formação Campestre", 13: "Formação Campestre", 84: "Formação Campestre",
    11: "Campo Alagado e Área Pantanosa",
    29: "Outros",
    14: "Agropecuária", 15: "Pastagem",
    18: "Agricultura", 19: "Agricultura", 39: "Agricultura",
    20: "Agricultura", 40: "Agricultura", 62: "Agricultura",
    41: "Agricultura", 36: "Agricultura", 46: "Agricultura",
    47: "Agricultura", 35: "Agricultura", 48: "Agricultura",
    9: "Silvicultura",
    21: "Mosaico de Usos",
    22: "Outros", 23: "Outros", 24: "Outros", 30: "Outros", 75: "Outros",
    91: "Outros", 25: "Outros", 26: "Outros", 33: "Outros", 31: "Outros",
    27: "Não observado",
}

_LULC_NIVEL_2 = {
    0: "Não observado",
    1: "Floresta",
    3: "Formação Florestal",
    4: "Formação Savânica",
    5: "Mangue",
    6: "Floresta Alagável",
    7: "Savana Alagada",
    49: "Restinga Arbórea",
    10: "Vegetação Herbácea e Arbustiva",
    11: "Campo Alagado e Área Pantanosa",
    12: "Formação Campestre",
    77: "Formação Herbáceo Arbustiva",
    32: "Apicum",
    29: "Afloramento Rochoso",
    50: "Restinga herbácea",
    13: "Outras Formações não Florestais",
    84: "Marisma",
    14: "Agropecuária",
    15: "Pastagem",
    18: "Agricultura", 19: "Agricultura", 39: "Agricultura",
    20: "Agricultura", 40: "Agricultura", 62: "Agricultura",
    41: "Agricultura", 36: "Agricultura", 46: "Agricultura",
    47: "Agricultura", 35: "Agricultura", 48: "Agricultura",
    9: "Silvicultura",
    21: "Mosaico de Usos",
    22: "Área não vegetada",
    23: "Praia, Duna e Areal",
    24: "Área Urbanizada",
    30: "Mineração",
    75: "Usina Fotovoltaica",
    91: "Energia Eólica",
    25: "Outras Áreas não Vegetadas",
    26: "Corpos D´água",
    33: "Rio, Lago e Oceano",
    31: "Aquicultura",
    27: "Não observado",
}

_LULC_NIVEL_3 = {
    0: "Não observado",
    1: "Floresta",
    3: "Formação Florestal",
    4: "Formação Savânica",
    5: "Mangue",
    6: "Floresta Alagável",
    7: "Savana Alagada",
    49: "Restinga Arbórea",
    10: "Formação Natural não Florestal",
    11: "Campo Alagado e Área Pantanosa",
    12: "Formação Campestre",
    77: "Formação Herbáceo Arbustiva",
    32: "Apicum",
    29: "Afloramento Rochoso",
    50: "Restinga herbácea",
    13: "Outras Formações não Florestais",
    84: "Marisma",
    14: "Agropecuária",
    15: "Pastagem",
    18: "Agricultura",
    19: "Lavoura Temporária", 39: "Lavoura Temporária", 20: "Lavoura Temporária",
    40: "Lavoura Temporária", 62: "Lavoura Temporária", 41: "Lavoura Temporária",
    36: "Lavoura Perene", 46: "Lavoura Perene", 47: "Lavoura Perene",
    35: "Lavoura Perene", 48: "Lavoura Perene",
    9: "Silvicultura",
    21: "Mosaico de Usos",
    22: "Área não vegetada",
    23: "Praia, Duna e Areal",
    24: "Área Urbanizada",
    30: "Mineração",
    75: "Usina Fotovoltaica",
    91: "Energia Eólica",
    25: "Outras Áreas não Vegetadas",
    26: "Corpos D´água",
    33: "Rio, Lago e Oceano",
    31: "Aquicultura",
    27: "Não observado",
}

_LULC_NIVEL_4 = {
    0: "Não observado",
    1: "Floresta",
    3: "Formação Florestal",
    4: "Formação Savânica",
    5: "Mangue",
    6: "Floresta Alagável",
    7: "Savana Alagada",
    49: "Restinga Arbórea",
    10: "Formação Natural não Florestal",
    11: "Campo Alagado e Área Pantanosa",
    12: "Formação Campestre",
    77: "Formação Herbáceo Arbustiva",
    32: "Apicum",
    29: "Afloramento Rochoso",
    50: "Restinga herbácea",
    13: "Outras Formações não Florestais",
    84: "Marisma",
    14: "Agropecuária",
    15: "Pastagem",
    18: "Agricultura",
    19: "Lavoura Temporária",
    39: "Soja", 20: "Cana", 40: "Arroz", 62: "Algodão",
    41: "Outras Lavouras Temporárias",
    36: "Lavoura Perene",
    46: "Café", 47: "Citrus", 35: "Dendê", 48: "Outras Lavouras Perenes",
    9: "Silvicultura",
    21: "Mosaico de Usos",
    22: "Área não Vegetada",
    23: "Praia, Duna e Areal",
    24: "Área Urbanizada",
    30: "Mineração",
    75: "Usina Fotovoltaica",
    91: "Energia Eólica",
    25: "Outras Áreas não Vegetadas",
    26: "Corpos D´água",
    33: "Rio, Lago e Oceano",
    31: "Aquicultura",
    27: "Não observado",
}

# Globais populadas em `connect` (após ee.Initialize)
BIOMAS_LEGEND = None
UF_NAMES = None
UF_SIGLAS = None
FOGO_SITUATION_MONTH = None
FOGO_MONTHS_STR = None
FOGO_MONTHS_INT = None
LULC_NIVEIS = None
LULC_NIVEL_0 = None
LULC_NIVEL_1 = None
LULC_NIVEL_1_1 = None
LULC_NIVEL_2 = None
LULC_NIVEL_3 = None
LULC_NIVEL_4 = None


# ---------------------------------------------------------------------------
# Redução agrupada por bioma, UF e classe (área + 3 gases numa só passada)
# ---------------------------------------------------------------------------
N_VALUES = 1 + len(GAS_BANDS)  # área + gases


def run_reduction(values_image, bioma_image, uf_image, class_image, geometry, scale):
    """values_image: bandas [area_ha, *GAS_BANDS], todas com a mesma máscara de fogo."""
    reducer = (ee.Reducer.sum().repeat(N_VALUES)
               .group(N_VALUES, "class").group(N_VALUES, "uf").group(N_VALUES, "bioma"))

    image_to_reduce = (values_image.addBands(bioma_image).addBands(uf_image)
                       .addBands(class_image.rename("class")))

    reduced_data = image_to_reduce.reduceRegion(
        reducer=reducer,
        geometry=geometry,
        scale=scale,
        maxPixels=MAX_PIXELS,
    )

    groups = ee.List(
        ee.Algorithms.If(reduced_data.contains("groups"), reduced_data.get("groups"), ee.List([]))
    )

    return ee.FeatureCollection(groups.map(convert_table)).flatten()


def convert_table(obj):
    obj = ee.Dictionary(obj)
    biome_id = obj.getNumber("bioma").int()
    biome_key = biome_id.format()
    uf_groups = ee.List(obj.get("groups"))

    def convert_uf(uf_obj):
        uf_obj = ee.Dictionary(uf_obj)
        uf_id = uf_obj.getNumber("uf").int()
        uf_key = uf_id.format()
        class_groups = ee.List(uf_obj.get("groups"))

        def to_feature(class_obj):
            class_obj = ee.Dictionary(class_obj)
            raw_class = class_obj.getNumber("class").int()
            month = raw_class.mod(100)
            class_id = raw_class.divide(100).int()
            sums = ee.List(class_obj.get("sum"))
            area_ha_val = ee.Number(sums.get(0))
            gas_vals = [ee.Number(sums.get(i + 1)) for i in range(len(GAS_BANDS))]
            total = gas_vals[0]
            for value in gas_vals[1:]:
                total = total.add(value)
            fid = biome_key.cat("_").cat(uf_key).cat("_").cat(raw_class.format())
            feat = (ee.Feature(None).set("id", fid).set("bioma_id", biome_id)
                    .set("Bioma", BIOMAS_LEGEND.get(biome_key)).set("uf_id", uf_id)
                    .set("UF", UF_NAMES.get(uf_key)).set("SIGLA_UF", UF_SIGLAS.get(uf_key))
                    .set("class_int", class_id).set("Níveis", LULC_NIVEIS.get(class_id))
                    .set("Nível 0", LULC_NIVEL_0.get(class_id))
                    .set("Nível 1", LULC_NIVEL_1.get(class_id))
                    .set("Nível 1_1", LULC_NIVEL_1_1.get(class_id))
                    .set("Nível 2", LULC_NIVEL_2.get(class_id))
                    .set("Nível 3", LULC_NIVEL_3.get(class_id))
                    .set("Nível 4", LULC_NIVEL_4.get(class_id))
                    .set("Área ha", area_ha_val).set("Área km²", area_ha_val.divide(100))
                    .set(TOTAL_COLUMN, total)
                    .set("Situação", FOGO_SITUATION_MONTH.get(month))
                    .set("Mês", FOGO_MONTHS_STR.get(month))
                    .set("mes", FOGO_MONTHS_INT.get(month)))
            for band, value in zip(GAS_BANDS, gas_vals):
                feat = feat.set(GAS_COLUMNS[band], value)
            return feat

        return ee.FeatureCollection(class_groups.map(to_feature))

    return ee.FeatureCollection(uf_groups.map(convert_uf)).flatten()


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def connect(project, account_profile=None):
    global BIOMAS_LEGEND, FOGO_SITUATION_MONTH, FOGO_MONTHS_STR, FOGO_MONTHS_INT
    global LULC_NIVEIS, LULC_NIVEL_0, LULC_NIVEL_1, LULC_NIVEL_1_1
    global LULC_NIVEL_2, LULC_NIVEL_3, LULC_NIVEL_4
    global UF_NAMES, UF_SIGLAS

    if account_profile:
        if auth is None:
            raise RuntimeError("BETA_PYTHON.auth não encontrado; não dá para usar --account-profile")
        print(f"Inicializando Earth Engine (perfil {account_profile!r}, project={project!r}) ...", flush=True)
        ee.Initialize(credentials=auth.load(account_profile), project=project)
    else:
        print(f"Inicializando Earth Engine com project={project!r} ...", flush=True)
        ee.Initialize(project=project)
    print("Conexão inicializada.\n", flush=True)

    BIOMAS_LEGEND = ee.Dictionary(_BIOMAS_LEGEND)
    UF_NAMES = ee.Dictionary(_UF_NAMES)
    UF_SIGLAS = ee.Dictionary(_UF_SIGLAS)
    FOGO_SITUATION_MONTH = ee.Dictionary(_FOGO_SITUATION_MONTH)
    FOGO_MONTHS_STR = ee.Dictionary(_FOGO_MONTHS_STR)
    FOGO_MONTHS_INT = ee.Dictionary(_FOGO_MONTHS_INT)
    LULC_NIVEIS = ee.Dictionary(_LULC_NIVEIS)
    LULC_NIVEL_0 = ee.Dictionary(_LULC_NIVEL_0)
    LULC_NIVEL_1 = ee.Dictionary(_LULC_NIVEL_1)
    LULC_NIVEL_1_1 = ee.Dictionary(_LULC_NIVEL_1_1)
    LULC_NIVEL_2 = ee.Dictionary(_LULC_NIVEL_2)
    LULC_NIVEL_3 = ee.Dictionary(_LULC_NIVEL_3)
    LULC_NIVEL_4 = ee.Dictionary(_LULC_NIVEL_4)


def build_inputs():
    # Pixel em hectares
    area_ha = ee.Image.pixelArea().divide(10000)

    # Emissões convertidas para total por pixel
    monitor_emiss = (
        ee.ImageCollection(EMISS_COLLECTION)
        .map(lambda img: img.select(GAS_BANDS).multiply(area_ha).float().copyProperties(img))
    )

    # LULC Coleção 11 (* 100 para compor com o mês)
    lulc = ee.Image(
        "projects/mapbiomas-public/assets/brazil/lulc/collection11/"
        "mapbiomas_brazil_collection11_coverage_v3"
    ).multiply(100)

    # Proxy para 2026 usando o último ano disponível da Coleção 11
    lulc = lulc.addBands(lulc.slice(-1).rename("classification_2026"))

    # Biomas e UFs do Brasil (IBGE)
    biomas = ee.FeatureCollection(
        "projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_biomas_IBGE_2026"
    )
    ufs = ee.FeatureCollection(
        "projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_ufs_IBGE_2025"
    )

    bounds = biomas.geometry().bounds()
    img_biomas = ee.Image().paint(biomas, "GEOCODE").rename("bioma")
    ufs_numeric = ufs.map(lambda f: ee.Feature(f).set("uf_id_num", ee.Number.parse(ee.Feature(f).get("CD_UF"))))
    img_ufs = ee.Image().paint(ufs_numeric, "uf_id_num").rename("uf")

    return area_ha, monitor_emiss, lulc, biomas, ufs, bounds, img_biomas, img_ufs


def process_month(year, month, area_ha, monitor_emiss, lulc, img_biomas, img_ufs, geometry, scale):
    """FeatureCollection de um único year_month (sem blend entre meses)."""
    ym_str = f"{year}_{month:02d}"
    lulc_year = lulc.select("classification_" + str(year))

    gases = monitor_emiss.filter(ee.Filter.eq("year_month", ym_str)).mosaic()
    # Pixel com fogo e emissão: mesmo critério da versão de uma banda (valor > 0),
    # aplicado à soma dos gases; todas as bandas compartilham essa máscara.
    fire_mask = gases.reduce(ee.Reducer.sum()).gt(0)
    gases = gases.unmask(0).updateMask(fire_mask)
    fire_month = ee.Image(month).updateMask(fire_mask).rename("month")

    fire_cover_month = fire_month.add(lulc_year).updateMask(fire_mask)
    values = area_ha.rename("area").updateMask(fire_mask).addBands(gases)

    fc = run_reduction(values, img_biomas, img_ufs, fire_cover_month, geometry, scale)
    return fc.map(lambda feat: feat.set("Ano", year))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true",
                        help="1 mês, região pequena, escala grosseira; imprime e não exporta")
    parser.add_argument("--submit", action="store_true",
                        help="submete as tasks de export; sem esta flag é apenas dry-run")
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--account-profile", default=None,
                        help="perfil de credencial isolada (ex.: workspace2); padrão usa a conta local")
    parser.add_argument("--scale", type=int, default=None,
                        help="escala em metros (padrão: 30; com --test: 300)")
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                        default=None, help="bbox do teste (W S E N)")
    parser.add_argument("--year", type=int, default=None, help="filtra por ano")
    parser.add_argument("--month", type=int, default=None, help="filtra por mês (1-12)")
    args = parser.parse_args()

    try:
        connect(args.project, args.account_profile)
    except Exception as error:
        print("Falha ao inicializar o Earth Engine:", error, file=sys.stderr)
        return 1

    area_ha, monitor_emiss, lulc, biomas, ufs, bounds, img_biomas, img_ufs = build_inputs()

    ym_list = monitor_emiss.aggregate_array("year_month").distinct().sort().getInfo()
    if not ym_list:
        print("Aviso: Nenhum 'year_month' encontrado na coleção monitor_emiss.")
        return 1

    all_year_months = [(int(p[0]), int(p[1])) for p in (str(ym).split("_") for ym in ym_list)]
    print(f"Meses disponíveis: {len(all_year_months)} "
          f"({all_year_months[0][0]}_{all_year_months[0][1]:02d} .. "
          f"{all_year_months[-1][0]}_{all_year_months[-1][1]:02d})")

    # filtros
    if args.year is not None or args.month is not None:
        year_months = [ym for ym in all_year_months
                       if (args.year is None or ym[0] == args.year)
                       and (args.month is None or ym[1] == args.month)]
        if not year_months:
            print("Nenhum year_month corresponde aos filtros.")
            return 1
    else:
        year_months = all_year_months

    # --- teste ----------------------------------------------------------------
    if args.test:
        scale = args.scale if args.scale is not None else 300
        geometry = (ee.Geometry.BBox(*args.bounds)
                    if args.bounds else ee.Geometry.BBox(-47.0, -15.0, -46.0, -14.0))
        if args.year is None and args.month is None:
            year, month = max(ym for ym in all_year_months if ym[0] <= 2025)
        else:
            year, month = year_months[-1]

        print(f"Teste: {year}_{month:02d} | escala {scale} m\n")
        fc = process_month(year, month, area_ha, monitor_emiss, lulc, img_biomas,
                           img_ufs, geometry, scale)
        print(f"Linhas finais: {fc.size().getInfo()}")
        for feat in fc.limit(10).getInfo().get("features", []):
            print(feat.get("properties"))
        return 0

    # --- export por mês -------------------------------------------------------
    scale = args.scale if args.scale is not None else SCALE
    geometry = bounds

    tasks = []
    for year, month in year_months:
        name = f"{DESCRIPTION}_{year}_{month:02d}"
        desc = TASK_PREFIX + name
        tasks.append((desc, name, year, month))

    print(f"\n{len(tasks)} task(s) | escala {scale} m\n")
    for desc, name, year, month in tasks:
        print(f"  {desc}  ->  {DRIVER_FOLDER}/{name}.csv")

    if not args.submit:
        print("\n[DRY-RUN] Nada foi submetido. Use --submit para enviar.")
        return 0

    submitted = 0
    for desc, name, year, month in tasks:
        fc = process_month(year, month, area_ha, monitor_emiss, lulc, img_biomas,
                           img_ufs, geometry, scale)
        task = ee.batch.Export.table.toDrive(
            collection=fc,
            description=desc,
            folder=DRIVER_FOLDER,
            fileNamePrefix=name,
            fileFormat="CSV",
            selectors=EXPORT_SELECTORS,
        )
        task.start()
        submitted += 1
        print(f"  submetida: {desc}  (id={task.id})")

    print(f"\n{submitted} task(s) submetida(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
