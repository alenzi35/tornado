#!/usr/bin/env python3
import os
import sys
import datetime
import numpy as np
import pygrib
import geopandas as gpd
from shapely.geometry import Point, Polygon

# -----------------------------
# Paths
# -----------------------------
DATA_DIR = "map/data"
CONUS_SHP = os.path.join(DATA_DIR, "ne_50m_admin_1_states_provinces_lakes.shp")
OUTPUT_CELLS = os.path.join(DATA_DIR, "tornado_prob_lcc.json")
OUTPUT_BORDERS = os.path.join(DATA_DIR, "borders_lcc.json")

# -----------------------------
# Target RAP cycle
# -----------------------------
target_date = datetime.datetime.utcnow()
target_cycle = f"{target_date:%Y%m%d} {target_date.hour:02d} F01"
print("=== TARGET CYCLE ===")
print("Using:", target_cycle)

# -----------------------------
# Download RAP GRIB
# -----------------------------
rap_url = f"https://noaa-rap-pds.s3.amazonaws.com/rap.{target_date:%Y%m%d}/rap.t{target_date.hour:02d}z.awip32f01.grib2"
print("URL:", rap_url)
print("RAP available. Downloading...")

grib_file = os.path.join(DATA_DIR, "rap.grib2")
os.system(f"wget -O {grib_file} {rap_url} -q --show-progress")
print("RAP downloaded.")

# -----------------------------
# Read GRIB
# -----------------------------
print("=== READING GRIB ===")
grbs = pygrib.open(grib_file)
grb = grbs[1]  # Example: first field
data = grb.values
lats, lons = grb.latlons()
print("GRIB loaded.")
print("Grid shape:", data.shape)

# -----------------------------
# Load CONUS outline
# -----------------------------
print("=== LOADING CONUS OUTLINE ===")
states = gpd.read_file(CONUS_SHP)
print("States loaded:", len(states))

# Filter to CONUS states
conus_states = [
    "Alabama","Arizona","Arkansas","California","Colorado","Connecticut",
    "Delaware","Florida","Georgia","Idaho","Illinois","Indiana","Iowa",
    "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts",
    "Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska",
    "Nevada","New Hampshire","New Jersey","New Mexico","New York",
    "North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania",
    "Rhode Island","South Carolina","South Dakota","Tennessee","Texas",
    "Utah","Vermont","Virginia","Washington","West Virginia","Wisconsin","Wyoming"
]

conus = states[states['name'].isin(conus_states)]
print("CONUS states filtered:", len(conus))

# -----------------------------
# Prepare cell polygons
# -----------------------------
print("=== FILTERING CELLS INSIDE CONUS ===")
cells = []

ny, nx = data.shape
for i in range(ny):
    for j in range(nx):
        lat = lats[i,j]
        lon = lons[i,j]
        point = Point(lon, lat)
        if any(poly.contains(point) for poly in conus.geometry):
            cells.append({
                "x": lon,
                "y": lat,
                "prob": float(data[i,j]),
                "dx": float(lons[0,1]-lons[0,0]),
                "dy": float(lats[1,0]-lats[0,0])
            })

print("Total cells inside CONUS:", len(cells))

# -----------------------------
# Save output
# -----------------------------
import json
with open(OUTPUT_CELLS, "w") as f:
    json.dump({"features": cells}, f)

print("Saved tornado_prob_lcc.json.")

# -----------------------------
# Generate simple border outlines
# -----------------------------
print("=== GENERATING BORDERS ===")
borders = []
for geom in conus.geometry:
    if geom.type == "Polygon":
        borders.append(list(geom.exterior.coords))
    elif geom.type == "MultiPolygon":
        for poly in geom.geoms:
            borders.append(list(poly.exterior.coords))

with open(OUTPUT_BORDERS, "w") as f:
    json.dump({"features": borders}, f)

print("Saved borders_lcc.json.")
print("Process complete.")
