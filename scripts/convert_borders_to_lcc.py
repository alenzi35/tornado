#!/usr/bin/env python3
"""
convert_borders_to_lcc.py

Download and process US Census TIGER national polygon
Clips to CONUS, keeps Great Lakes as holes,
projects to Lambert Conformal Conic, outputs JSON
"""

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path

# Output JSON
OUT_PATH = Path("map/data/borders_lcc.json")

# TIGER nation shapefile (2023, generalized 20m)
TIGER_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/"
    "cb_2023_us_nation_20m.shp.zip"
)

# CONUS bbox (lon/lat)
CONUS_BBOX = {
    "min_lon": -125,
    "max_lon": -66,
    "min_lat": 24,
    "max_lat": 50,
}

# RAP Lambert Conformal Conic (same as your map)
LCC_PROJ4 = (
    "+proj=lcc "
    "+lat_1=33 +lat_2=45 +lat_0=39 "
    "+lon_0=-96 "
    "+x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)


def download_shapefile(url, folder):
    """Download and unzip a shapefile, return a GeoDataFrame."""
    print(f"Downloading {url}")
    resp = requests.get(url)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    extract_dir = Path(folder)
    extract_dir.mkdir(parents=True, exist_ok=True)
    z.extractall(extract_dir)

    shp_file = next(extract_dir.glob("*.shp"))
    print("Loaded:", shp_file)
    return gpd.read_file(shp_file)


def main():

    # 1) Download TIGER nation polygon
    nation = download_shapefile(TIGER_URL, "tmp_tiger")

    # 2) Clip to CONUS bbox
    nation_conus = nation.cx[
        CONUS_BBOX["min_lon"]:CONUS_BBOX["max_lon"],
        CONUS_BBOX["min_lat"]:CONUS_BBOX["max_lat"],
    ]

    # 3) Reproject to LCC
    nation_lcc = nation_conus.to_crs(LCC_PROJ4)

    # 4) Extract polygons with holes (lake holes preserved)
    features = []

    for geom in nation_lcc.geometry:

        if geom is None:
            continue

        # Polygons can have holes
        if geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                # exterior
                features.append(list(poly.exterior.coords))
                # holes (interiors)
                for interior in poly.interiors:
                    features.append(list(interior.coords))

        elif geom.geom_type == "Polygon":
            features.append(list(geom.exterior.coords))
            for interior in geom.interiors:
                features.append(list(interior.coords))

    # 5) Write JSON
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
            "units": "m",
        },
        "features": features,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f)

    print(f"Saved {len(features)} polygons (outline + holes) to {OUT_PATH}")


if __name__ == "__main__":
    main()
