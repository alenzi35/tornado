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
from shapely.geometry import box
from shapely.prepared import prep

from pyproj import Proj

# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

INTERCEPT = -14

COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}

COUNTRIES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
LAKES_URL = "https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_lakes.zip"

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

# ================= URL =================

RAP_URL = (
    f"https://noaa-rap-pds.s3.amazonaws.com/"
    f"rap.{DATE}/rap.t{HOUR}z.awip32f{FCST}.grib2"
)

print("Target:", DATE, HOUR, "F01")
print("URL:", RAP_URL)

# ================= CHECK FILE EXISTS =================

def url_exists(url):
    r = requests.head(url)
    return r.status_code == 200

if not url_exists(RAP_URL):
    print("RAP file not ready yet. Skipping.")
    exit(0)

print("RAP file available. Processing.")

# ================= DOWNLOAD =================

urllib.request.urlretrieve(RAP_URL, GRIB_PATH)

# ================= LOAD GRIB =================

grbs = pygrib.open(GRIB_PATH)

def pick_var(grbs, shortname, typeOfLevel=None, bottom=None, top=None):
    for g in grbs:
        if g.shortName.lower() != shortname.lower():
            continue
        if typeOfLevel and g.typeOfLevel != typeOfLevel:
            continue
        if bottom is not None and top is not None:
            if not hasattr(g, "bottomLevel"):
                continue
            if not (abs(g.bottomLevel - bottom) < 1 and abs(g.topLevel - top) < 1):
                continue
        return g
    raise RuntimeError(f"{shortname} not found")

grbs.seek(0)
cape_msg = pick_var(grbs, "cape", "surface")
grbs.seek(0)
cin_msg = pick_var(grbs, "cin", "surface")
grbs.seek(0)
hlcy_msg = pick_var(grbs, "hlcy", "heightAboveGroundLayer", 0, 1000)

cape = np.nan_to_num(cape_msg.values)
cin = np.nan_to_num(cin_msg.values)
hlcy = np.nan_to_num(hlcy_msg.values)

# ================= LAT/LON =================

lats, lons = cape_msg.latlons()

# ================= PROJECTION =================

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

# ================= PROB =================

linear = INTERCEPT + COEFFS["CAPE"] * cape + COEFFS["CIN"] * cin + COEFFS["HLCY"] * hlcy
prob = 1 / (1 + np.exp(-linear))

# ================= LOAD CONUS MASK =================

def download_shapefile(url, folder):
    resp = requests.get(url)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall(folder)
    shp_file = [f for f in z.namelist() if f.endswith(".shp")][0]
    return gpd.read_file(f"{folder}/{shp_file}")

print("Downloading country borders...")
countries = download_shapefile(COUNTRIES_URL, "tmp_countries")

print("Downloading lakes...")
lakes = download_shapefile(LAKES_URL, "tmp_lakes")

print("Building CONUS mask...")

usa = countries[countries["ADMIN"] == "United States of America"]

great_lakes_names = [
    "Lake Superior",
    "Lake Michigan",
    "Lake Huron",
    "Lake Erie",
    "Lake Ontario"
]

great_lakes = lakes[lakes["name"].isin(great_lakes_names)]

usa_geom = usa.geometry.unary_union
lakes_geom = great_lakes.geometry.unary_union

conus_geom = usa_geom.difference(lakes_geom)

# ================= REPROJECT MASK =================

conus_lcc = gpd.GeoSeries([conus_geom], crs="EPSG:4326").to_crs(proj_lcc.srs).iloc[0]
prepared_conus = prep(conus_lcc)

print("CONUS mask ready.")

# ================= FILTER GRID CELLS =================

print("Filtering grid cells...")

features = []

rows, cols = prob.shape

for i in range(rows):
    for j in range(cols):
        x = x_vals[i, j]
        y = y_vals[i, j]

        dx = x_vals[i, j+1] - x if j < cols-1 else x - x_vals[i, j-1]
        dy = y_vals[i+1, j] - y if i < rows-1 else y - y_vals[i-1, j]

        dx = abs(dx)
        dy = abs(dy)

        cell = box(x, y, x + dx, y + dy)

        # STRICT: keep only if centroid inside CONUS
        if not prepared_conus.contains(cell.centroid):
            continue

        features.append({
            "x": float(x),
            "y": float(y),
            "dx": float(dx),
            "dy": float(dy),
            "prob": float(prob[i, j])
        })

print(f"Kept {len(features)} CONUS cells.")

# ================= OUTPUT =================

valid_start = f"{int(HOUR):02d}:00"
valid_end = f"{(int(HOUR)+1)%24:02d}:00"

output = {
    "run_date": DATE,
    "run_hour": HOUR,
    "forecast": "F01",
    "valid": f"{valid_start}-{valid_end} UTC",
    "generated": datetime.datetime.utcnow().isoformat() + "Z",
    "projection": params,
    "features": features
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f)

print("Saved:", OUTPUT_JSON)
print("Done.")
