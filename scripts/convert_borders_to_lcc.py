#!/usr/bin/env python3
"""
convert_borders_to_lcc.py

Downloads Natural Earth borders, filters to USA only,
projects to Lambert Conformal Conic, and exports GeoJSON.
No lakes included.
"""

import geopandas as gpd
import requests
import zipfile
import io
from pathlib import Path

# Output path
OUTPUT_PATH = Path("data/borders_lcc.geojson")

# Lambert Conformal Conic projection (CONUS standard)
LCC_PROJ = {
    "proj": "lcc",
    "lat_1": 33,
    "lat_2": 45,
    "lat_0": 39,
    "lon_0": -96,
    "x_0": 0,
    "y_0": 0,
    "datum": "WGS84",
    "units": "m",
    "no_defs": True,
}

COUNTRY_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
STATE_LINES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces_lines.zip"


def download_shapefile(url):
    print(f"Downloading {url}")
    response = requests.get(url)
    response.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(response.content))

    extract_dir = Path("temp") / Path(url).stem
    extract_dir.mkdir(parents=True, exist_ok=True)

    z.extractall(extract_dir)

    shp_file = next(extract_dir.glob("*.shp"))
    return gpd.read_file(shp_file)


def main():

    # Download datasets
    countries = download_shapefile(COUNTRY_URL)
    state_lines = download_shapefile(STATE_LINES_URL)

    # Filter to USA only
    countries = countries[
        countries["admin"] == "United States of America"
    ]

    state_lines = state_lines[
        state_lines["adm0_name"] == "United States of America"
    ]

    # Convert country polygon to boundary line
    country_border = countries.boundary

    # Combine country border + state borders
    combined = gpd.GeoDataFrame(
        geometry=list(country_border.geometry) + list(state_lines.geometry),
        crs="EPSG:4326"
    )

    # Project to Lambert Conformal Conic
    combined = combined.to_crs(LCC_PROJ)

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Save
    combined.to_file(OUTPUT_PATH, driver="GeoJSON")

    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
