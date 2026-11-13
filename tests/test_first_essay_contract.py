from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "gee" / "primeiro_ensaio.js"
REFERENCE = ROOT / "gee" / "reference" / "primeiro_ensaio_uma_banda.js"


class FirstEssayContractTest(unittest.TestCase):
    def test_current_script_uses_qcn_2019_and_exports_three_bands_per_month(self):
        script = CURRENT.read_text(encoding="utf-8")

        self.assertIn(
            'ee.Image("projects/ee-ipam/assets/SEEG/SEEG14/RETIFICACAO/c_rect_col11_2019")',
            script,
        )
        self.assertIn("'emiss_CO2'", script)
        self.assertIn("'emiss_CO2e_CH4'", script)
        self.assertIn("'emiss_CO2e_N2O'", script)
        self.assertIn("Export.image.toAsset({", script)
        self.assertIn("image:img,", script)

    def test_script_does_not_serialize_or_stack_all_months_for_debugging(self):
        script = CURRENT.read_text(encoding="utf-8")

        self.assertNotIn("print('monthly_list_collection'", script)
        self.assertNotIn("monthly_list_collection.toBands()", script)
        self.assertNotIn("ImageCollection(monthly_list_collection)", script)

    def test_single_band_version_is_preserved_as_reference(self):
        script = REFERENCE.read_text(encoding="utf-8")

        self.assertIn(
            "qcn_brazil_historical_biomass_carbon_qcn_rect_v1", script
        )
        self.assertIn(".rename(burned.bandNames())", script)


if __name__ == "__main__":
    unittest.main()
