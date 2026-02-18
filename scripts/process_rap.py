#!/usr/bin/env python3
import os
import sys
import requests
import pygrib
import numpy as np
import xarray as xr
import geopandas as gpd
from shapely.geometry import Point, box

# ----------------------------
# Paths
# ----------------------------
DATA_DIR = "map/data"
CONUS_SHP = os.path.join(DATA_DIR, "ne_10m_admin_1_states.shp")  # keep all 4 shapefile files together
TORNADO_JSON = os.path.join(DATA_DIR, "tornado_prob.json")
TORNADO_LCC_JSON = os.path.join(DATA_DIR, "tornado_prob_lcc.json")

# ----------------------------
# Target cycle
# ----------------------------
TARGET_CYCLE = "20260218"
TARGET_HOUR = "21"
FORECAST_FHOUR = "01"

# Example RAP URL
RAP_URL = f"https://noaa-rap-pds.s3.amazonaws.com/rap.{TARGET_CYCLE}/rap.t{TARGET_HOUR}z.awip32f{FORECAST_FHOUR}.grib2"

# ----------------------------
# Diagnostics
# ----------------------------
print("=== TARGET CYCLE ===")
print(f"Using: {TARGET_CYCLE} {TARGET_HOUR} F{FORECAST_FHOUR}")
print(f"URL: {RAP_URL}")

# ----------------------------
# Download RAP
# ----------------------------
response = requests.get(RAP_URL)
if response.status_code != 200:
    print("RAP unavailable, exiting.")
    sys.exit(1)

with open("temp.grib2", "wb") as f:
    f.write(response.content)

print("RAP downloaded.")

# ----------------------------
# Read GRIB
# ----------------------------
grbs = pygrib.open("temp.grib2")

# Example: extract max 3s wind gust probability (replace with your variable)
grb = grbs[1]  # adjust index for the variable
lats, lons = grb.latlons()
values = grb.values

print("GRIB loaded.")
print(f"Grid shape: {values.shape}")

# ----------------------------
# Load CONUS outline
# ----------------------------
print("=== LOADING CONUS OUTLINE ===")
states = gpd.read_file(CONUS_SHP)

# Filter for CONUS only
conus_states = states[~states['name'].isin(['Alaska', 'Hawaii', 'Puerto Rico'])]
conus = conus_states.dissolve()  # merge all geometries into one

print("CONUS outline loaded.")
print(f"CONUS bounds: {conus.total_bounds}")

# ----------------------------
# Create cell points & filter by CONUS
# ----------------------------
ny, nx = values.shape
cells = []

for j in range(ny):
    for i in range(nx):
        val = float(values[j, i])
        if np.isnan(val):
            continue
        point = Point(lons[j, i], lats[j, i])
        if conus.geometry.iloc[0].contains(point) or conus.geometry.iloc[0].touches(point):
            cells.append({
                "x": float(lons[j, i]),
                "y": float(lats[j, i]),
                "prob": val
            })

print(f"Total cells inside CONUS: {len(cells)}")

# ----------------------------
# Save as JSON
# ----------------------------
import json

with open(TORNADO_JSON, "w") as f:
    json.dump({"features": cells}, f)

print(f"Tornado probabilities saved to {TORNADO_JSON}")

# ----------------------------
# Convert to LCC (dummy example, adjust your conversion)
# ----------------------------
# Here we would normally call your LCC conversion logic
# For example, if you have convert_to_lcc(cells), you can loop over cells
# For now just copy the same JSON to LCC version
with open(TORNADO_LCC_JSON, "w") as f:
    json.dump({"features": cells}, f)

print(f"LCC tornado probabilities saved to {TORNADO_LCC_JSON}")
