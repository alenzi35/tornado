import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
import requests
import geopandas as gpd
from pyproj import Proj
from shapely.geometry import Point

# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

CONUS_SHP = "map/data/ne_50m_admin_1_states_provinces_lakes.shp"  # Your 50m shapefile

INTERCEPT = -14
COEFFS = {"CAPE": 2.88592370e-03, "CIN": 2.38728498e-05, "HLCY": 8.85192696e-03}

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

RAP_URL = f"https://noaa-rap-pds.s3.amazonaws.com/rap.{DATE}/rap.t{HOUR}z.awip32f{FCST}.grib2"
print("=== TARGET CYCLE ===")
print("Using:", DATE, HOUR, "F01")
print("URL:", RAP_URL)

# ================= CHECK IF FILE EXISTS =================

def url_exists(url):
    r = requests.head(url)
    return r.status_code == 200

if not url_exists(RAP_URL):
    print("RAP file not ready yet. Skipping.")
    exit(0)

# ================= DOWNLOAD =================

urllib.request.urlretrieve(RAP_URL, GRIB_PATH)
print("RAP downloaded.")

# ================= OPEN GRIB =================

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

# ================= LOAD DATA =================

grbs.seek(0)
cape_msg = pick_var(grbs, "cape", "surface")
grbs.seek(0)
cin_msg = pick_var(grbs, "cin", "surface")
grbs.seek(0)
hlcy_msg = pick_var(grbs, "hlcy", "heightAboveGroundLayer", 0, 1000)

cape = np.nan_to_num(cape_msg.values)
cin = np.nan_to_num(cin_msg.values)
hlcy = np.nan_to_num(hlcy_msg.values)

lats, lons = cape_msg.latlons()

params = cape_msg.projparams
proj_lcc = Proj(proj="lcc", lat_1=params["lat_1"], lat_2=params["lat_2"],
                lat_0=params["lat_0"], lon_0=params["lon_0"],
                a=params.get("a", 6371229), b=params.get("b", 6371229))
x_vals, y_vals = proj_lcc(lons, lats)

# ================= LOAD CONUS SHAPE =================

print("=== LOADING CONUS OUTLINE ===")
states = gpd.read_file(CONUS_SHP)

# Keep only CONUS (exclude Alaska, Hawaii, PR, etc.)
CONUS_STATES = [
    "AL","AZ","AR","CA","CO","CT","DE","FL","GA","ID","IL","IN","IA","KS","KY","LA",
    "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC",
    "ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"
]
states = states[states["postal"].isin(CONUS_STATES)]

# ================= FEATURES =================

features = []
rows, cols = prob.shape = cape.shape

for i in range(rows):
    for j in range(cols):
        x = x_vals[i, j]
        y = y_vals[i, j]

        dx = x_vals[i, j+1] - x if j < cols-1 else x - x_vals[i, j-1]
        dy = y_vals[i+1, j] - y if i < rows-1 else y - y_vals[i-1, j]

        pt = Point(x, y)
        inside = states.contains(pt).any()
        if not inside:
            continue

        linear = INTERCEPT + COEFFS["CAPE"] * cape[i,j] + COEFFS["CIN"] * cin[i,j] + COEFFS["HLCY"] * hlcy[i,j]
        prob = 1 / (1 + np.exp(-linear))

        features.append({
            "x": float(x),
            "y": float(y),
            "dx": float(abs(dx)),
            "dy": float(abs(dy)),
            "prob": float(prob)
        })

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

print("Updated:", OUTPUT_JSON)
