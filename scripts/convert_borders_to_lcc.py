#!/usr/bin/env python3
"""
convert_borders_to_lcc.py

Downloads Natural Earth borders, filters to CONUS USA,
projects to Lambert Conformal Conic, and outputs JSON.
Includes:
- CONUS country outline
- State borders
- Great Lakes preserved
"""

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path

OUT_PATH = Path("map/data/borders_lcc.json")

COUNTRY_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
STATE_LINES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces_lines.zip"

# Lambert Conformal Conic projection parameters
LCC_PROJ4 = (
    "+proj=lcc "
    "+lat_1=33 +lat_2=45 +lat_0=39 "
    "+lon_0=-96 "
    "+x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)


def download_shapefile(url, folder):
    print(f"Downloading {url}")
    resp = requests.get(url)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    extract_dir = Path(folder)
    extract_dir.mkdir(parents=True, exist_ok=True)
    z.extractall(extract_dir)
    shp_file = next(extract_dir.glob("*.shp"))
    return gpd.read_file(shp_file)


def main():
    # Load datasets
    countries = download_shapefile(COUNTRY_URL, "tmp_countries")
    states = download_shapefile(STATE_LINES_URL, "tmp_states")

    # Filter to CONUS USA only
    countries = countries[countries["admin"] == "United States of America"]
    # <-- NOTE: state lines use adm0_name, NOT admin
    states = states[states["adm0_name"] == "United States of America"]

    # Bounding box for CONUS
    min_lon, max_lon = -125, -66
    min_lat, max_lat = 24, 50
    countries = countries.cx[min_lon:max_lon, min_lat:max_lat]
    states = states.cx[min_lon:max_lon, min_lat:max_lat]

    # Convert country polygons to boundary lines
    country_borders = countries.boundary

    # Combine country + state lines
    combined = gpd.GeoDataFrame(
        geometry=list(country_borders.geometry) + list(states.geometry),
        crs="EPSG:4326"
    )

    # Project to LCC
    combined = combined.to_crs(LCC_PROJ4)

    # Export as JSON
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    features = []
    for geom in combined.geometry:
        # handle LineString or MultiLineString
        if geom.type == "LineString":
            coords = list(geom.coords)
            features.append(coords)
        elif geom.type == "MultiLineString":
            for line in geom.geoms:
                coords = list(line.coords)
                features.append(coords)

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

    print(f"Saved {len(features)} border lines to {OUT_PATH}")


if __name__ == "__main__":
    main()
