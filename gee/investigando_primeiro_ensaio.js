/**
 * Investiga qual mapa de carbono foi usado nos resultados mensais do primeiro
 * ensaio. Recalcula meses escolhidos com os dois mapas e compara, por bioma e
 * classe, o erro absoluto ponderado por área em relação ao asset FIRE_EMISS.
 *
 * Execute no Earth Engine Code Editor. Ajuste YEAR_MONTHS; exportação Drive
 * opcional e desligada por padrão.
 */
// Comece com um mês e escala 300 m para inspeção rápida. Para comparação
// nacional exata, use SCALE=30, habilite EXPORT_TO_DRIVE e inicie a task.
var YEAR_MONTHS = ['2019-01'];
var SCALE = 300;
var EXPORT_TO_DRIVE = false;
var DRIVE_FOLDER = 'monitoramento-sentinel';
// Opcional: fixe um recorte para comparar em 30 m sem reduzir o Brasil inteiro.
// Exemplo: ee.Geometry.BBox(-47, -15, -46, -14). null usa os biomas do Brasil.
var TEST_REGION = null;

var CARBON_MAPS = [
  {
    label: 'qcn_original',
    asset: 'projects/ee-ipam/assets/CCAL/public/qcn/qcn_brazil_historical_biomass_carbon_qcn_rect_v1'
  },
  {
    label: 'c_rect_col11_2019',
    asset: 'projects/ee-ipam/assets/SEEG/SEEG14/RETIFICACAO/c_rect_col11_2019'
  }
];

var monthlyBurned = ee.ImageCollection(
  'projects/mapbiomas-public/assets/brazil/fire/monitor/mapbiomas_fire_monthly_burned_v1'
);
var existingEmissions = ee.ImageCollection(
  'projects/ee-ipam/assets/MAPBIOMAS/FIRE/MONITOR/FIRE_EMISS/v00'
);
var coverage = ee.Image(
  'projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3'
);
var biomes = ee.FeatureCollection(
  'projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_biomas_IBGE_2026'
);
var areaHa = ee.Image.pixelArea().divide(10000);
var biomeImage = ee.Image().paint(biomes, 'GEOCODE').rename('bioma');
var biomeLegend = ee.Dictionary({
  '1': 'Amazônia', '2': 'Caatinga', '3': 'Cerrado',
  '4': 'Mata Atlântica', '5': 'Pampa', '6': 'Pantanal'
});

// Mantidos exatamente os fatores e agrupamentos do primeiro_ensaio.js.
var factors = {
  'Amazônia': {
    'Agricultura': {cf:0.9, c_pool:'AGB', c_mean:9.909136},
    'Pastagem': {cf:0.866, c_pool:'AGB', c_mean:9.909136},
    'Formação Campestre': {cf:0.866, c_pool:'AGB+DW+LI', c_mean:11.87611},
    'Campo Alagado e Área Pantanosa': {cf:0.866, c_pool:'AGB+DW+LI', c_mean:11.87611},
    'Formação Savânica': {cf:0.666, c_pool:'0.26*AGB+DW+LI', c_mean:10.5953496},
    'Formação Florestal': {cf:0.663, c_pool:'DW+LI', c_mean:14.555805}
  },
  'Cerrado': {
    'Agricultura': {cf:0.9, c_pool:'AGB', c_mean:9.444437},
    'Pastagem': {cf:0.607, c_pool:'AGB', c_mean:9.444437},
    'Formação Campestre': {cf:0.607, c_pool:'AGB+DW+LI', c_mean:11.814823},
    'Campo Alagado e Área Pantanosa': {cf:0.607, c_pool:'AGB+DW+LI', c_mean:11.814823},
    'Formação Savânica': {cf:0.666, c_pool:'0.26*AGB+DW+LI', c_mean:27.405347},
    'Formação Florestal': {cf:0.656, c_pool:'DW+LI', c_mean:12.530418}
  },
  'Mata Atlântica': {
    'Agricultura': {cf:0.9, c_pool:'AGB', c_mean:7.960108},
    'Pastagem': {cf:0.769, c_pool:'AGB', c_mean:7.960108},
    'Formação Campestre': {cf:0.769, c_pool:'AGB+DW+LI', c_mean:25.037944},
    'Campo Alagado e Área Pantanosa': {cf:0.769, c_pool:'AGB+DW+LI', c_mean:25.037944},
    'Formação Savânica': {cf:0.666, c_pool:'0.26*AGB+DW+LI', c_mean:8.0815222},
    'Formação Florestal': {cf:0.663, c_pool:'DW+LI', c_mean:11.409046}
  },
  'Pantanal': {
    'Agricultura': {cf:0.9, c_pool:'AGB', c_mean:9.938581},
    'Pastagem': {cf:0.6925, c_pool:'AGB', c_mean:9.938581},
    'Formação Campestre': {cf:0.6925, c_pool:'AGB+DW+LI', c_mean:12.371491},
    'Campo Alagado e Área Pantanosa': {cf:0.6925, c_pool:'AGB+DW+LI', c_mean:12.371491},
    'Formação Savânica': {cf:0.666, c_pool:'0.26*AGB+DW+LI', c_mean:12.6971932},
    'Formação Florestal': {cf:0.656, c_pool:'DW+LI', c_mean:16.180421}
  },
  'Caatinga': {
    'Agricultura': {cf:0.9, c_pool:'AGB', c_mean:9.049347},
    'Pastagem': {cf:0.649, c_pool:'AGB', c_mean:9.049347},
    'Formação Campestre': {cf:0.649, c_pool:'AGB+DW+LI', c_mean:11.561256},
    'Campo Alagado e Área Pantanosa': {cf:0.649, c_pool:'AGB+DW+LI', c_mean:11.561256},
    'Formação Savânica': {cf:0.666, c_pool:'0.26*AGB+DW+LI', c_mean:7.9012824},
    'Formação Florestal': {cf:0.85075, c_pool:'DW+LI', c_mean:10.723852}
  },
  'Pampa': {
    'Agricultura': {cf:0.9, c_pool:'AGB', c_mean:11.1815},
    'Pastagem': {cf:0.944, c_pool:'AGB', c_mean:11.1815},
    'Formação Campestre': {cf:0.944, c_pool:'AGB+DW+LI', c_mean:15.788241},
    'Campo Alagado e Área Pantanosa': {cf:0.944, c_pool:'AGB+DW+LI', c_mean:15.788241},
    'Formação Savânica': {cf:0.666, c_pool:'0.26*AGB+DW+LI', c_mean:0},
    'Formação Florestal': {cf:0.656, c_pool:'DW+LI', c_mean:4.606741}
  }
};
var classes = {
  'Formação Florestal':[3,6,5,49,9], 'Formação Savânica':[4,77,50],
  'Formação Campestre':[12,7], 'Campo Alagado e Área Pantanosa':[11],
  'Pastagem':[15,21], 'Agricultura':[39,20,40,62,41,46,47,35,48]
};
var anthropic = ['Pastagem', 'Agricultura'];

function buildCandidate(carbon, burned, year) {
  var coverageYear = coverage.select('classification_' + year);
  var recipe = ee.Image(0);
  Object.keys(factors).forEach(function(biomeName) {
    var biome = biomes.filter(ee.Filter.eq('Bioma', biomeName));
    // Preserva a máscara/semântica do script original.
    var biomeMask = ee.Image().paint(biome).eq(0);
    Object.keys(factors[biomeName]).forEach(function(className) {
      var spec = factors[biomeName][className];
      var classMask = coverageYear.eq(classes[className]).reduce('max');
      var carbonForClass = anthropic.indexOf(className) === -1
        ? carbon
        : ee.Image(spec.c_mean).rename('AGB')
            .addBands(ee.Image(0).rename('CDW'))
            .addBands(ee.Image(0).rename('LITTER'));
      var calculated = carbonForClass.expression({
        expression: spec.c_pool,
        map: {
          AGB: carbonForClass.select('AGB'),
          DW: carbonForClass.select('CDW'),
          LI: carbonForClass.select('LITTER')
        }
      }).multiply(spec.cf);
      recipe = recipe.where(classMask.and(burned).and(biomeMask), calculated);
    });
  });
  return recipe;
}

function summarizeDifference(month, lulcYear, burned, observed, candidate, assetLabel) {
  var errorTonnes = candidate.subtract(observed).abs()
    .multiply(areaHa).updateMask(burned).rename('error_t');
  var reducer = ee.Reducer.sum().group(1, 'class').group(1, 'bioma');
  var stats = errorTonnes.addBands(biomeImage)
    .addBands(coverage.select('classification_' + lulcYear).rename('class'))
    .reduceRegion({
      reducer: reducer,
      geometry: TEST_REGION || biomes.geometry().bounds(),
      scale: SCALE,
      maxPixels: 1e13,
      tileScale: 4
    });
  var biomeGroups = ee.List(ee.Algorithms.If(stats.contains('groups'), stats.get('groups'), ee.List([])));
  return ee.FeatureCollection(biomeGroups.map(function(biomeObj) {
    biomeObj = ee.Dictionary(biomeObj);
    var biomeId = biomeObj.getNumber('bioma').int();
    var classGroups = ee.List(biomeObj.get('groups'));
    return ee.FeatureCollection(classGroups.map(function(classObj) {
      classObj = ee.Dictionary(classObj);
      return ee.Feature(null).set({
        'year_month': month,
        'carbon_candidate': assetLabel,
        'bioma_id': biomeId,
        'Bioma': biomeLegend.get(biomeId.format()),
        'class_int': classObj.getNumber('class').int(),
        'abs_error_tonnes': classObj.getNumber('sum')
      });
    }));
  })).flatten();
}

function processMonth(month) {
  var parts = month.split('-');
  var year = Number(parts[0]);
  var monthNumber = Number(parts[1]);
  var burnedName = 'brazil-' + year + '-' + monthNumber;
  var existingKey = year + '_' + ('0' + monthNumber).slice(-2);
  var burnedImage = ee.Image(monthlyBurned.filter(ee.Filter.eq('name', burnedName)).first());
  var existingImage = ee.Image(existingEmissions.filter(ee.Filter.eq('year_month', existingKey)).first())
    .select('FireMonth');
  // O ensaio usava classificação 2025 como proxy para fogo em 2026.
  var lulcYear = year === 2026 ? 2025 : year;
  var burnedMask = burnedImage.gt(0);
  var results = CARBON_MAPS.map(function(mapSpec) {
    return summarizeDifference(
      existingKey, lulcYear, burnedMask, existingImage,
      buildCandidate(ee.Image(mapSpec.asset), burnedMask, lulcYear), mapSpec.label
    );
  });
  return ee.FeatureCollection(results).flatten();
}

var comparison = ee.FeatureCollection(YEAR_MONTHS.map(processMonth)).flatten();

if (EXPORT_TO_DRIVE) {
  Export.table.toDrive({
    collection: comparison,
    description: 'investigando_primeiro_ensaio_carbon_map_comparison',
    folder: DRIVE_FOLDER,
    fileNamePrefix: 'investigando_primeiro_ensaio_carbon_map_comparison',
    fileFormat: 'CSV',
    selectors: ['year_month', 'carbon_candidate', 'bioma_id', 'Bioma', 'class_int', 'abs_error_tonnes']
  });
} else {
  print('Erro absoluto por mês × candidato × bioma × classe (toneladas)', comparison);
  print('Soma do erro por candidato (menor deve indicar maior proximidade):',
    comparison.reduceColumns({
      selectors: ['carbon_candidate', 'abs_error_tonnes'],
      reducer: ee.Reducer.sum().group(0, 'carbon_candidate')
    })
  );
}
