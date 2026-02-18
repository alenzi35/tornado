import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
import requests
import geopandas as gpd
from shapely.geometry import Point
from pyproj import Proj, CRS


# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"
CONUS_PATH = "map/data/conus_lcc.json"

INTERCEPT = -14

COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs("map/data", exist_ok=True)


# ================= TIME LOGIC =================

now = datetime.datetime.utcnow()
run_time = now - datetime.timedelta(hours=1)

DATE = run_time.strftime("%Y%m%d")
HOUR = run_time.strftime("%H")
FCST = "01"

print("\n=== TARGET CYCLE ===")
print("Using:", DATE, HOUR, "F01")


RAP_URL = (
    f"https://noaa-rap-pds.s3.amazonaws.com/"
    f"rap.{DATE}/rap.t{HOUR}z.awip32f{FCST}.grib2"
)

print("URL:", RAP_URL)


# ================= CHECK FILE EXISTS =================

r = requests.head(RAP_URL)

if r.status_code != 200:
    print("RAP not ready. Exiting.")
    exit(0)

print("RAP available. Downloading...")


urllib.request.urlretrieve(RAP_URL, GRIB_PATH)


# ================= OPEN GRIB =================

print("\n=== READING GRIB ===")

grbs = pygrib.open(GRIB_PATH)


def pick_var(shortname):
    grbs.seek(0)
    for g in grbs:
        if g.shortName.lower() == shortname.lower():
            return g
    raise RuntimeError(f"{shortname} not found")


cape_msg = pick_var("cape")
cin_msg  = pick_var("cin")
hlcy_msg = pick_var("hlcy")


cape = np.nan_to_num(cape_msg.values)
cin  = np.nan_to_num(cin_msg.values)
hlcy = np.nan_to_num(hlcy_msg.values)

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


# ================= PROBABILITY =================

linear = (
    INTERCEPT +
    COEFFS["CAPE"] * cape +
    COEFFS["CIN"]  * cin +
    COEFFS["HLCY"] * hlcy
)

prob = 1 / (1 + np.exp(-linear))


# ================= LOAD CONUS POLYGON =================

print("\n=== LOADING CONUS OUTLINE ===")

conus = gpd.read_file(CONUS_PATH)

print("CONUS geometry loaded.")


# ================= FILTER CELLS =================

print("\n=== FILTERING CELLS TO CONUS ===")

features = []

rows, cols = prob.shape
total_cells = rows * cols
kept_cells = 0

for i in range(rows):
    for j in range(cols):

        point = Point(x_vals[i, j], y_vals[i, j])

        if not point.intersects(conus.geometry.iloc[0]):
            continue

        kept_cells += 1

        features.append({
            "x": float(x_vals[i, j]),
            "y": float(y_vals[i, j]),
            "prob": float(prob[i, j])
        })


print("Total RAP cells:", total_cells)
print("Cells inside CONUS:", kept_cells)


# ================= OUTPUT =================

output = {
    "run_date": DATE,
    "run_hour": HOUR,
    "forecast": "F01",
    "generated": datetime.datetime.utcnow().isoformat() + "Z",
    "projection": params,
    "features": features
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f)

print("\nSaved:", OUTPUT_JSON)
print("Done.\n")
