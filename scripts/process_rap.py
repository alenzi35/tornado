import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
import requests
import zipfile
import io

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep
from pyproj import Proj

# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

INTERCEPT = -6.274846902965728

COEFFS = {
    "CAPE": 0.0007852504286701655,
    "CIN": -0.003028035273017941,
    "HLCY": 0.008318690761993085,
    "DEPR": -0.0045
}

CONUS_SHAPE_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs("map/data", exist_ok=True)

# ================= TIME LOGIC =================

def get_target_cycle():
    now = datetime.datetime.utcnow()
    run_time = now - datetime.timedelta(hours=1)
    date = run_time.strftime("%Y%m%d")
    hour = run_time.strftime("%H")
    return date, hour

DATE, HOUR = get_target_cycle()
FCST = "01"

# ================= DOWNLOAD RAP 32km =================

RAP_URL = f"https://noaa-rap-pds.s3.amazonaws.com/rap.{DATE}/rap.t{HOUR}z.awip32f{FCST}.grib2"

print("Target:", DATE, HOUR, "F01")
print("URL:", RAP_URL)

def url_exists(url):
    r = requests.head(url)
    return r.status_code == 200

if not url_exists(RAP_URL):
    print("RAP file not ready yet. Skipping.")
    exit(0)

urllib.request.urlretrieve(RAP_URL, GRIB_PATH)
print("Downloaded RAP GRIB2")

# ================= LOAD GRIB =================

grbs = pygrib.open(GRIB_PATH)

def pick_var(grbs, shortName=None, typeOfLevel=None, level=None, topLevel=None):
    for g in grbs:
        match_short = shortName is None or g.shortName.lower() == shortName.lower()
        match_type = typeOfLevel is None or g.typeOfLevel.lower() == typeOfLevel.lower()
        match_level = level is None or getattr(g, "level", None) == level
        match_top = topLevel is None or getattr(g, "topLevel", None) == topLevel
        if match_short and match_type and match_level and match_top:
            return g
    raise RuntimeError(
        f"Variable not found: shortName={shortName}, typeOfLevel={typeOfLevel}, level={level}, topLevel={topLevel}"
    )

# ================= EXTRACT VARIABLES =================

# CAPE
grbs.seek(0)
cape_msg = pick_var(grbs, shortName="cape")

# CIN
grbs.seek(0)
cin_msg = pick_var(grbs, shortName="cin")

# Helicity (0-1 km) - adjust layer if needed
grbs.seek(0)
hlcy_msg = pick_var(grbs, shortName="hlcy", typeOfLevel="heightAboveGroundLayer", level=0, topLevel=1000)

# Dewpoint depression fallback
grbs.seek(0)
try:
    depr_msg = pick_var(grbs, shortName="depr")
    depr = np.nan_to_num(depr_msg.values)
except:
    t2_msg = pick_var(grbs, shortName="2t", typeOfLevel="heightAboveGround", level=2)
    d2_msg = pick_var(grbs, shortName="2d", typeOfLevel="heightAboveGround", level=2)
    t2 = np.nan_to_num(t2_msg.values)
    d2 = np.nan_to_num(d2_msg.values)
    depr = t2 - d2

cape = np.nan_to_num(cape_msg.values)
cin = np.nan_to_num(cin_msg.values)
hlcy = np.nan_to_num(hlcy_msg.values)

# U/V 10 m
grbs.seek(0)
u10_msg = pick_var(grbs, shortName="10u", typeOfLevel="heightAboveGround", level=10)
v10_msg = pick_var(grbs, shortName="10v", typeOfLevel="heightAboveGround", level=10)
u10 = np.nan_to_num(u10_msg.values)
v10 = np.nan_to_num(v10_msg.values)

# U/V 500 mb
grbs.seek(0)
u500_msg = pick_var(grbs, shortName="u", typeOfLevel="isobaricInhPa", level=500)
v500_msg = pick_var(grbs, shortName="v", typeOfLevel="isobaricInhPa", level=500)
u500 = np.nan_to_num(u500_msg.values)
v500 = np.nan_to_num(v500_msg.values)

# ================= COORDS =================

lats, lons = cape_msg.latlons()
params = cape_msg.projparams

proj_lcc = Proj(
    proj="lcc",
    lat_1=params["lat_1"],
    lat_2=params["lat_2"],
    lat_0=params["lat_0"],
    lon_0=params["lon_0"],
    a=params.get("a", 6371229),
    b=params.get("b", 6371229)
)

x_vals, y_vals = proj_lcc(lons, lats)

# ================= MODEL =================

logit = (
    INTERCEPT
    + COEFFS["CAPE"] * cape
    + COEFFS["CIN"] * cin
    + COEFFS["HLCY"] * hlcy
    + COEFFS["DEPR"] * depr
)

prob = 1 / (1 + np.exp(-logit))

# ================= LOAD CONUS SHAPE =================

print("Downloading CONUS shapefile...")

r = requests.get(CONUS_SHAPE_URL)
z = zipfile.ZipFile(io.BytesIO(r.content))
z.extractall(DATA_DIR)

shp_path = None
for f in os.listdir(DATA_DIR):
    if f.endswith(".shp"):
        shp_path = os.path.join(DATA_DIR, f)
        break

states = gpd.read_file(shp_path)
exclude = ["AK", "HI", "PR", "GU", "VI", "MP", "AS"]
states = states[~states["STUSPS"].isin(exclude)]
conus = states.unary_union
prepared = prep(conus)

# ================= GRID FILTER =================

ny, nx = prob.shape
dx = x_vals[0,1] - x_vals[0,0]
dy = y_vals[1,0] - y_vals[0,0]

features = []

for i in range(ny):
    for j in range(nx):
        p = float(prob[i,j])
        if p < 0.02:
            continue

        lon = lons[i,j]
        lat = lats[i,j]

        if not prepared.contains(Point(lon, lat)):
            continue

        x = x_vals[i,j]
        y = y_vals[i,j]

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [x - dx/2, y - dy/2],
                    [x + dx/2, y - dy/2],
                    [x + dx/2, y + dy/2],
                    [x - dx/2, y + dy/2],
                    [x - dx/2, y - dy/2]
                ]]
            },
            "properties": {"p": p}
        })

geojson = {
    "type": "FeatureCollection",
    "projection": {  # added for convert_borders_to_lcc.py
        "proj": "lcc",
        "lat_1": params["lat_1"],
        "lat_2": params["lat_2"],
        "lat_0": params["lat_0"],
        "lon_0": params["lon_0"],
        "a": params.get("a", 6371229),
        "b": params.get("b", 6371229)
    },
    "features": features
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(geojson, f)

print("Saved tornado probability GeoJSON")
