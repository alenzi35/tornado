import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
import requests
from pyproj import Proj
import geopandas as gpd
from shapely.geometry import Point

# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

CONUS_SHP = "map/data/ne_50m_admin_1_states_provinces_lakes.shp"

INTERCEPT = -14
COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs("map/data", exist_ok=True)

# ================= TIME LOGIC =================

def get_target_cycle():
    """
    We want: (current hour - 1)z F01
    Example: Now = 14:20 → use 13z F01 → valid 14–15
    """
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

print("RAP available. Downloading...")

# ================= DOWNLOAD =================

urllib.request.urlretrieve(RAP_URL, GRIB_PATH)
print("RAP downloaded.")

# ================= OPEN GRIB =================

grbs = pygrib.open(GRIB_PATH)
print("=== READING GRIB ===")

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
cin  = np.nan_to_num(cin_msg.values)
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

# ================= LOAD CONUS =================

print("=== LOADING CONUS OUTLINE ===")
conus = gpd.read_file(CONUS_SHP)

# Clean invalid geometries
conus["geometry"] = conus["geometry"].apply(lambda g: g.buffer(0) if not g.is_valid else g)

# Optional: keep only CONUS states
CONUS_NAMES = [
    "Alabama","Arizona","Arkansas","California","Colorado","Connecticut",
    "Delaware","Florida","Georgia","Idaho","Illinois","Indiana","Iowa",
    "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts",
    "Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska",
    "Nevada","New Hampshire","New Jersey","New Mexico","New York",
    "North Carolina","North Dakota","Ohio","Oklahoma","Oregon",
    "Pennsylvania","Rhode Island","South Carolina","South Dakota",
    "Tennessee","Texas","Utah","Vermont","Virginia","Washington",
    "West Virginia","Wisconsin","Wyoming"
]
conus = conus[conus["name"].isin(CONUS_NAMES)]

# Convert CRS to GRIB projection
conus = conus.to_crs(cape_msg.projparams)

# Create union polygon safely
conus_union = conus.geometry.values.union_all()

# ================= PROBABILITY =================

linear = INTERCEPT + COEFFS["CAPE"]*cape + COEFFS["CIN"]*cin + COEFFS["HLCY"]*hlcy
prob = 1 / (1 + np.exp(-linear))

# ================= FEATURES =================

features = []
rows, cols = prob.shape

for i in range(rows):
    for j in range(cols):
        x = x_vals[i, j]
        y = y_vals[i, j]
        dx = x_vals[i, j+1]-x if j < cols-1 else x - x_vals[i,j-1]
        dy = y_vals[i+1,j]-y if i < rows-1 else y - y_vals[i-1,j]

        # Only keep points inside CONUS
        if not conus_union.contains(Point(x,y)):
            continue

        features.append({
            "x": float(x),
            "y": float(y),
            "dx": float(abs(dx)),
            "dy": float(abs(dy)),
            "prob": float(prob[i,j])
        })

# ================= OUTPUT =================

valid_start = f"{int(HOUR):02d}:00"
valid_end = f"{(int(HOUR)+1)%24:02d}:00"

output = {
    "run_date": DATE,
    "run_hour": HOUR,
    "forecast": "F01",
    "valid": f"{valid_start}-{valid_end} UTC",
    "generated": datetime.datetime.utcnow().isoformat()+"Z",
    "projection": params,
    "features": features
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f)

print("Updated:", OUTPUT_JSON)
