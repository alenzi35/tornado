#!/usr/bin/env python3
"""
convert_borders_to_lcc.py

Download and process US Cartographic Boundary (5m) polygon.
Keeps Great Lakes as holes, projects to Lambert Conformal Conic,
outputs JSON for map rendering.
"""

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path

# -----------------------------
# Output path
# -----------------------------
OUT_PATH = Path("map/data/borders_lcc.json")

# -----------------------------
# Cartographic Boundary US Nation (5m resolution)
# -----------------------------
CARTO_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_nation_5m.zip"

# -----------------------------
# RAP Lambert Conformal Conic projection
# -----------------------------
LCC_PROJ4 = (
    "+proj=lcc "
    "+lat_1=33 +lat_2=45 +lat_0=39 "
    "+lon_0=-96 "
    "+x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)

# -----------------------------
# Helper function: download + unzip shapefile
# -----------------------------
def download_shapefile(url, folder):
    print(f"Downloading {url} …")
    resp = requests.get(url)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    extract_dir = Path(folder)
    extract_dir.mkdir(parents=True, exist_ok=True)
    z.extractall(extract_dir)

    shp_file = next(extract_dir.glob("*.shp"))
    print(f"Shapefile loaded: {shp_file}")
    return gpd.read_file(shp_file)

# -----------------------------
# Main
# -----------------------------
def main():
    # 1) Download shapefile
    nation = download_shapefile(CARTO_URL, "tmp_us_nation")

    # 2) Reproject to LCC
    nation_lcc = nation.to_crs(LCC_PROJ4)

    # 3) Extract polygons with holes
    features = []

    for geom in nation_lcc.geometry:
        if geom is None:
            continue

        if geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                # exterior
                features.append(list(poly.exterior.coords))
                # interiors (lake holes)
                for interior in poly.interiors:
                    features.append(list(interior.coords))

        elif geom.geom_type == "Polygon":
            # exterior
            features.append(list(geom.exterior.coords))
            # interiors
            for interior in geom.interiors:
                features.append(list(interior.coords))

    # 4) Write JSON
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    out = {
        "projection": {
            "proj": "lcc",
            "lat_1": 33,
            "lat_2": 45,
            "lat_0": 39,
            "lon_0": -96,
            "x_0": 0,
            "y_0": 0,
            "datum": "WGS84",
            "units": "m"
        },
        "features": features
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f)

    print(f"Saved {len(features)} polygons (outline + holes) to {OUT_PATH}")


if __name__ == "__main__":
    main()
