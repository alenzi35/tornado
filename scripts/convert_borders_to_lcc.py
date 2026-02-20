#!/usr/bin/env python3

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path
from pyproj import CRS, Transformer
import xarray as xr

# -----------------------------
# Paths
# -----------------------------
OUT_PATH = Path("map/data/borders_lcc.json")
TMP_FOLDER = Path("tmp_borders")

NE_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces.zip"

# -----------------------------
# RAP grid info (must match process_rap.py)
# -----------------------------
# These values come from your GRIB projection + cell spacing
X0 = -2699020.142521929
Y0 = -1588819.031011287
DX = 13000.0
DY = 13000.0
NX = 451
NY = 337

# -----------------------------
# Load RAP projection from GRIB
# -----------------------------
import pygrib
import urllib.request

GRIB_PATH = "data/rap.grib2"

# Try to download the RAP file if missing
if not Path(GRIB_PATH).exists():
    print("RAP GRIB not found. Skipping download, cannot get projection.")
    exit(1)

grbs = pygrib.open(GRIB_PATH)
msg = grbs.message(1)
params = msg.projparams

# RAP projection CRS
rap_crs = CRS.from_proj4(
    f"+proj=lcc +lat_1={params['lat_1']} +lat_2={params['lat_2']} "
    f"+lat_0={params['lat_0']} +lon_0={params['lon_0']} "
    f"+a={params.get('a', 6371229)} +b={params.get('b', 6371229)} +units=m +no_defs"
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
# Convert to grid coordinates
# -----------------------------
def proj_to_grid(x, y):
    gx = (x - X0) / DX
    gy = (y - Y0) / DY
    return gx, gy

def convert_geom(geom):
    rings = []

    if geom.geom_type == "Polygon":
        rings.append(geom.exterior.coords)
        for hole in geom.interiors:
            rings.append(hole.coords)
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            rings.append(poly.exterior.coords)
            for hole in poly.interiors:
                rings.append(hole.coords)

    result = []
    for ring in rings:
        converted = [proj_to_grid(x, y) for x, y in ring]
        result.append(converted)

    return result

features = []
for geom in gdf.geometry:
    features.extend(convert_geom(geom))

# -----------------------------
# Save JSON
# -----------------------------
OUT_PATH.parent.mkdir(exist_ok=True)
with open(OUT_PATH, "w") as f:
    json.dump({
        "nx": NX,
        "ny": NY,
        "features": features
    }, f)

print(f"Saved {len(features)} borders to {OUT_PATH}")
print("Done.")
