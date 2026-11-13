var historical_carbon = ee.Image("projects/ee-ipam/assets/SEEG/SEEG14/RETIFICACAO/c_rect_col11_2019");
var monthly_burned = ee.ImageCollection('projects/mapbiomas-public/assets/brazil/fire/monitor/mapbiomas_fire_monthly_burned_v1');
var coverage = ee.Image('projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3');
var biomas = ee.FeatureCollection('projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_biomas_IBGE_2026');

var biomas_mask = ee.Image().paint(biomas).eq(0);
var biomas_bounds = biomas.geometry().bounds();

print('historical_carbon',historical_carbon);

// OBS: O fator de combustão (cf) utilizado de maneira padronizada para Agricultura
// é o fator utilizado para algodão no terceiro inventario (0.9). O mesmo utilizado pelo IMAFLORA

//atenção na camada de carbono: c_pool ´é usado para Agricultura e Pastagem, c_mean ´é usado para cobertura de nativas

var fatoresEmissaoPorBioma = {
  "Amazônia": {
    "Agricultura": { "cf": 0.9, "c_pool": "AGB", "c_mean": 9.909136 },
    "Pastagem": { "cf": 0.866, "c_pool": "AGB", "c_mean": 9.909136 },
    "Formação Campestre": { "cf": 0.866, "c_pool": "AGB+DW+LI", "c_mean": 11.87611 },
    "Campo Alagado e Área Pantanosa": { "cf": 0.866, "c_pool": "AGB+DW+LI", "c_mean": 11.87611 },
    "Formação Savânica": { "cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 10.5953496 },
    "Formação Florestal": { "cf": 0.663, "c_pool": "DW+LI", "c_mean": 14.555805 }
  },
  "Cerrado": {
    "Agricultura": { "cf": 0.9, "c_pool": "AGB", "c_mean": 9.444437 },
    "Pastagem": { "cf": 0.607, "c_pool": "AGB", "c_mean": 9.444437 },
    "Formação Campestre": { "cf": 0.607, "c_pool": "AGB+DW+LI", "c_mean": 11.814823 },
    "Campo Alagado e Área Pantanosa": { "cf": 0.607, "c_pool": "AGB+DW+LI", "c_mean": 11.814823 },
    "Formação Savânica": { "cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 27.405347 },
    "Formação Florestal": { "cf": 0.656, "c_pool": "DW+LI", "c_mean": 12.530418 }
  },
  "Mata Atlântica": {
    "Agricultura": { "cf": 0.9, "c_pool": "AGB", "c_mean": 7.960108 },
    "Pastagem": { "cf": 0.769, "c_pool": "AGB", "c_mean": 7.960108 },
    "Formação Campestre": { "cf": 0.769, "c_pool": "AGB+DW+LI", "c_mean": 25.037944 },
    "Campo Alagado e Área Pantanosa": { "cf": 0.769, "c_pool": "AGB+DW+LI", "c_mean": 25.037944 },
    "Formação Savânica": { "cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 8.0815222 },
    "Formação Florestal": { "cf": 0.663, "c_pool": "DW+LI", "c_mean": 11.409046 }
  },
  "Pantanal": {
    "Agricultura": { "cf": 0.9, "c_pool": "AGB", "c_mean": 9.938581 },
    "Pastagem": { "cf": 0.6925, "c_pool": "AGB", "c_mean": 9.938581 },
    "Formação Campestre": { "cf": 0.6925, "c_pool": "AGB+DW+LI", "c_mean": 12.371491 },
    "Campo Alagado e Área Pantanosa": { "cf": 0.6925, "c_pool": "AGB+DW+LI", "c_mean": 12.371491 },
    "Formação Savânica": { "cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 12.6971932 },
    "Formação Florestal": { "cf": 0.656, "c_pool": "DW+LI", "c_mean": 16.180421 }
  },
  "Caatinga": {
    "Agricultura": { "cf": 0.9, "c_pool": "AGB", "c_mean": 9.049347 },
    "Pastagem": { "cf": 0.649, "c_pool": "AGB", "c_mean": 9.049347 },
    "Formação Campestre": { "cf": 0.649, "c_pool": "AGB+DW+LI", "c_mean": 11.561256 },
    "Campo Alagado e Área Pantanosa": { "cf": 0.649, "c_pool": "AGB+DW+LI", "c_mean": 11.561256 },
    "Formação Savânica": { "cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 7.9012824 },
    "Formação Florestal": { "cf": 0.85075, "c_pool": "DW+LI", "c_mean": 10.723852 }
  },
  "Pampa": {
    "Agricultura": { "cf": 0.9, "c_pool": "AGB", "c_mean": 11.1815 },
    "Pastagem": { "cf": 0.944, "c_pool": "AGB", "c_mean": 11.1815 },
    "Formação Campestre": { "cf": 0.944, "c_pool": "AGB+DW+LI", "c_mean": 15.788241 },
    "Campo Alagado e Área Pantanosa": { "cf": 0.944, "c_pool": "AGB+DW+LI", "c_mean": 15.788241 },
    "Formação Savânica": { "cf": 0.666, "c_pool": "0.26*AGB+DW+LI", "c_mean": 0 },
    "Formação Florestal": { "cf": 0.656, "c_pool": "DW+LI", "c_mean": 4.606741 }
  }
};

var fatoresPorGas = {
  "CO2": {
    "Formação Florestal": 1580,
    "Formação Savânica": 1613,
    "Formação Campestre": 1613,
    "Campo Alagado e Área Pantanosa": 1613,
    "Pastagem": 1613,
    "Agricultura": 1515
  },
  "CH4": {
    "Formação Florestal": 6.8,
    "Formação Savânica": 2.3,
    "Formação Campestre": 2.3,
    "Campo Alagado e Área Pantanosa": 2.3,
    "Pastagem": 2.3,
    "Agricultura": 2.7
  },
  "N2O": {
    "Formação Florestal": 0.2,
    "Formação Savânica": 0.2,
    "Formação Campestre": 0.2,
    "Campo Alagado e Área Pantanosa": 0.2,
    "Pastagem": 0.2,
    "Agricultura": 0.07 // OBS: Fatores de agricultura vieram do IPCC (Tabela 2.5)
  }
};

// definir o fator de conversão para CO2 equivalente, GWPAR5
var factor_convert_CO2e = {
  'CH4':28,
  'N2O':265
};


var classes_list = {
  "Formação Florestal":[3,6,5,49,9],
  "Formação Savânica":[4,77,50],
  "Formação Campestre":[12,7],
  "Campo Alagado e Área Pantanosa":[11],
  "Pastagem":[15,21],
  "Agricultura":[39,20,40,62,41,46,47,35,48]
};

var antropic_list = ["Pastagem","Agricultura"];

Map.addLayer(coverage,{},'coverage',false);
Map.addLayer(biomas,{},'biomas',false);
Map.addLayer(historical_carbon,{},'historical_carbon',false);
// Map.addLayer(monthly_burned,{},'monthly_burned');
Map.addLayer(monthly_burned.toBands(),{},'monthly_burned 2 ');

var biomas_list = Object.keys(fatoresEmissaoPorBioma);
var coverage_list = Object.keys(fatoresEmissaoPorBioma['Amazônia']);

monthly_burned.aggregate_array('name').sort().evaluate(function(monthly_list){

  monthly_list.forEach(function(year_month){

    var burned = monthly_burned.filter(ee.Filter.eq('name',year_month)).first();

    var split = year_month.split('-');

    var year = split[1] === '2026' ? '2025' : split[1];

    var coverage_year = coverage.select('classification_' + year);

    var recipes = {
      'CO2':ee.Image(0),
      'CH4':ee.Image(0),
      'N2O':ee.Image(0),
    }

    biomas_list.forEach(function(bioma_str){
      var bioma = biomas.filter(ee.Filter.eq('Bioma',bioma_str));
      var bioma_mask = ee.Image().paint(bioma).eq(0);
      coverage_list.forEach(function(coverage_str){
        var classes = classes_list[coverage_str];

        var coverage_binary = coverage_year.eq(classes).reduce('max');

        var obj = fatoresEmissaoPorBioma[bioma_str][coverage_str]
        var c_pool = obj['c_pool']
        var cf = obj['cf']

        var mean_carbon = ee.Image(obj['c_mean']).rename('AGB')
          .addBands(ee.Image(0).rename('CDW'))
          .addBands(ee.Image(0).rename('LITTER'))

        var carbon = antropic_list.indexOf(coverage_str) === -1 ? historical_carbon : mean_carbon

        var calculate = carbon.expression({
          expression:c_pool,
          map:{
            'AGB':carbon.select('AGB'),
            // 'BGB':carbon.select('BGB'),
            'DW':carbon.select('CDW'),
            'LI':carbon.select('LITTER'),
            // 'TOTAL':carbon.select('TOTAL'),
          }
        });

        calculate = calculate.multiply(cf);

        //////////////

        var factor_carbon_biomass = 0.47;

        var biomass_calculate_ton_ha = calculate.multiply(factor_carbon_biomass);

        var area_ha = ee.Image.pixelArea().divide(10000);

        var biomass_calculate_ton = biomass_calculate_ton_ha.multiply(area_ha);

        var biomass_calculate_kg = biomass_calculate_ton.multiply(1000);

        [
          'CO2','CH4','N2O'
          // 'emiss_CO2','emiss_CO2e_CH4','emiss_CO2e_N2O'
        ].forEach(function(gas){

          var fator_gas_coverage = fatoresPorGas[gas][coverage_str];

          var gas_calculate_gramas = biomass_calculate_kg.multiply(fator_gas_coverage);

          var gas_name = 'emiss_' + gas;

          if (factor_convert_CO2e[gas] !== undefined){
            gas_calculate_gramas = gas_calculate_gramas.multiply(factor_convert_CO2e[gas]);

            gas_name = 'emiss_CO2e_' + gas;
          }

          var gas_calculate_t_ha = gas_calculate_gramas.divide(1000000).divide(area_ha).float();

          recipes[gas] = recipes[gas].where(coverage_binary.and(burned).and(bioma_mask),gas_calculate_t_ha)
            .rename(gas_name);

        });

        // recipe = recipe.where(coverage_binary.and(burned).and(bioma_mask),calculate);


      });

    });



    var recipe = ee.Image().select();

    [
      'CO2','CH4','N2O'
    ].forEach(function(gas){
      recipe = recipe.addBands(recipes[gas]);
    });


    var description = "co2_fire_emiss_" + split[1] + '_' + (('0'+split[2]).slice(-2));
    var time_start = ee.Date(ee.String(description.slice(-7).replace('_','-')).cat('-').cat('01'));

    // print('split[1]',split[1]);


    var assetId = "projects/ee-ipam/assets/MAPBIOMAS/FIRE/MONITOR/FIRE_EMISS/v00/" + description;


    var img = recipe
      .copyProperties(burned)
      //.selfMask()
      .set({
        "metric":'CO2 equivalent',
        "unit":"t/ha",
        "month":description.slice(-2),
        "year_month":description.slice(-7),
        "name":description,
        "system:index":description,
        "system:time_start":time_start.millis(),
        "system:time_end":time_start.advance(1,'month').millis(),
      });


    Export.image.toAsset({
      image:img,
      description:'WS_IPAM_SEEG-'+description,
      assetId:assetId,
      pyramidingPolicy:'median',
      // dimensions:,
      region:biomas_bounds,
      scale:30,
      // crs:,
      // crsTransform:,
      maxPixels:1e13,
      // shardSize:,
      // priority:,
      // overwrite:true
    })


  });

  print('Monthly three-band export tasks created:', monthly_list.length);
});
