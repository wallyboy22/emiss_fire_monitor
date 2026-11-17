"""Baixa e simplifica os contornos usados nos mapas da página de destaques.

  - biomas: IBGE (asset do GEE), simplificados a ~3 km
  - UFs:    malha do IBGE (servicodados, qualidade mínima)

Saída: data/geo/biomas.geojson e data/geo/ufs.geojson (coordenadas com 3 casas).
Rodar uma vez; o build_dashboard.py só lê os arquivos.
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "geo"
BIOMAS = "projects/ee-ipam/assets/ORIGINAIS/IBGE/limite_biomas_IBGE_2026"
UF_URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
          "?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=UF")
UF_META = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 3), round(coords[1], 3)]
    return [_round(c) for c in coords]


def biomas(ccal_root):
    sys.path.insert(0, str(ccal_root))
    import ee
    try:
        from BETA_PYTHON import auth
        ee.Initialize(credentials=auth.load("workspace2"), project="mapbiomas-brazil")
    except ImportError:
        ee.Initialize(project="mapbiomas-brazil")
    fc = ee.FeatureCollection(BIOMAS).map(
        lambda f: ee.Feature(f.geometry(maxError=1000).simplify(maxError=3000), {"cd": f.get("CD_BIOMA")}))
    feats = []
    for f in fc.getInfo()["features"]:
        g = f["geometry"]
        if g["type"] == "GeometryCollection":  # fica só com os polígonos
            polys = [p for sub in g["geometries"] if sub["type"] in ("Polygon", "MultiPolygon")
                     for p in ([sub["coordinates"]] if sub["type"] == "Polygon" else sub["coordinates"])]
            g = {"type": "MultiPolygon", "coordinates": polys}
        feats.append({"type": "Feature", "properties": {"cd": int(f["properties"]["cd"])},
                      "geometry": {"type": g["type"], "coordinates": _round(g["coordinates"])}})
    return {"type": "FeatureCollection", "features": feats}


def ufs():
    gj = json.load(urllib.request.urlopen(UF_URL))
    meta = {int(e["id"]): e["sigla"] for e in json.load(urllib.request.urlopen(UF_META))}
    for f in gj["features"]:
        code = int(f["properties"]["codarea"])
        f["properties"] = {"cd": code, "sigla": meta[code]}
        f["geometry"]["coordinates"] = _round(f["geometry"]["coordinates"])
    return gj


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ccal = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "CCAL"
    (OUT / "ufs.geojson").write_text(json.dumps(ufs(), separators=(",", ":")), encoding="utf-8")
    (OUT / "biomas.geojson").write_text(json.dumps(biomas(ccal), separators=(",", ":")), encoding="utf-8")
    for p in OUT.glob("*.geojson"):
        print(p, p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
