#!/usr/bin/env python3

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path
from pyproj import CRS

# -----------------------------
# Paths
# -----------------------------
OUT_PATH = Path("map/data/borders_lcc.json")
TMP_FOLDER = Path("tmp_borders")

NE_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces.zip"

# -----------------------------
# RAP LCC projection (matches process_rap.py)
# -----------------------------
# You can hardcode RAP params or extract from GRIB; here we hardcode example values
rap_crs = CRS.from_proj4(
    "+proj=lcc +lat_1=50 +lat_2=50 +lat_0=50 +lon_0=253 "
    "+a=6371229 +b=6371229 +units=m +no_defs"
)

# -----------------------------
# Download and load Natural Earth shapefile
# -----------------------------
print("Downloading Natural Earth borders...")
TMP_FOLDER.mkdir(exist_ok=True)

resp = requests.get(NE_URL)
resp.raise_for_status()
z = zipfile.ZipFile(io.BytesIO(resp.content))
z.extractall(TMP_FOLDER)

shp_path = TMP_FOLDER / "ne_50m_admin_1_states_provinces.shp"
gdf = gpd.read_file(shp_path)

# -----------------------------
# Filter to USA only
# -----------------------------
gdf = gdf[gdf["admin"] == "United States of America"]

# -----------------------------
# Reproject borders to RAP CRS
# -----------------------------
gdf = gdf.to_crs(rap_crs)

# -----------------------------
# Convert geometries to list of coordinates (in meters)
# -----------------------------
features = []

for geom in gdf.geometry:
    if geom.geom_type == "Polygon":
        features.append(list(geom.exterior.coords))
        for hole in geom.interiors:
            features.append(list(hole.coords))
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            features.append(list(poly.exterior.coords))
            for hole in poly.interiors:
                features.append(list(hole.coords))

# -----------------------------
# Save JSON
# -----------------------------
OUT_PATH.parent.mkdir(exist_ok=True)
with open(OUT_PATH, "w") as f:
    json.dump({
        "features": features
    }, f)

print(f"Saved {len(features)} borders to {OUT_PATH}")
print("Done.")
