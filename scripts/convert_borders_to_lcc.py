#!/usr/bin/env python3
"""
convert_borders_to_lcc.py

Robust version for GitHub Actions:
- Downloads Natural Earth borders
- Filters to CONUS USA (lower 48)
- Preserves Great Lakes
- Combines country + state borders
- Projects to Lambert Conformal Conic
- Outputs JSON
"""

import geopandas as gpd
import requests
import zipfile
import io
from pathlib import Path
import json

OUT_PATH = Path("map/data/borders_lcc.json")

COUNTRY_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
STATE_LINES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces_lines.zip"

LCC_PROJ4 = (
    "+proj=lcc "
    "+lat_1=33 +lat_2=45 +lat_0=39 "
    "+lon_0=-96 "
    "+x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)

CONUS_BBOX = {
    "min_lon": -125,
    "max_lon": -66,
    "min_lat": 24,
    "max_lat": 50
}


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


def filter_usa(df):
    """
    Filter a GeoDataFrame to United States rows.
    Uses 'ADMIN' column, case-insensitive substring match.
    """
    if "ADMIN" not in df.columns:
        raise RuntimeError(f"'ADMIN' column not found in {df.columns}")
    return df[df["ADMIN"].str.contains("United States", case=False, na=False)]


def clip_conus(df):
    return df.cx[CONUS_BBOX["min_lon"]:CONUS_BBOX["max_lon"],
                 CONUS_BBOX["min_lat"]:CONUS_BBOX["max_lat"]]


def extract_coords(combined_gdf):
    features = []
    for geom in combined_gdf.geometry:
        if geom is None:
            continue
        if geom.type == "LineString":
            features.append(list(geom.coords))
        elif geom.type == "MultiLineString":
            for line in geom.geoms:
                features.append(list(line.coords))
    return features


def main():
    # Download datasets
    countries = download_shapefile(COUNTRY_URL, "tmp_countries")
    states = download_shapefile(STATE_LINES_URL, "tmp_states")

    # Filter to USA
    countries = filter_usa(countries)
    states = filter_usa(states)

    # Clip to CONUS bounding box
    countries = clip_conus(countries)
    states = clip_conus(states)

    # Convert country polygons to boundary lines
    country_borders = countries.boundary

    # Combine country + state lines
    combined = gpd.GeoDataFrame(
        geometry=list(country_borders.geometry) + list(states.geometry),
        crs="EPSG:4326"
    )

    # Project to LCC
    combined = combined.to_crs(LCC_PROJ4)

    # Extract coordinates
    features = extract_coords(combined)

    # Ensure output directory exists
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Save JSON
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
