import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
from pyproj import Proj

# ================= CONFIG =================
DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

# Logistic regression coefficients
INTERCEPT = -14
COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}

# ================= SETUP =================
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs("map/data", exist_ok=True)

# ================= TIME LOGIC =================
FCST = 1  # 1-hour forecast

now = datetime.datetime.utcnow()
# Determine RAP run (hourly, completed ~50min after)
run_time = now.replace(minute=0, second=0, microsecond=0)
if now.minute < 55:
    run_time -= datetime.timedelta(hours=1)  # previous hour if before :55

DATE = run_time.strftime("%Y%m%d")
HOUR = run_time.strftime("%H")

# Forecast valid time = run + forecast hour
valid_time = run_time + datetime.timedelta(hours=FCST)
VALID_START = valid_time.strftime("%H")
VALID_END = (valid_time + datetime.timedelta(hours=1)).strftime("%H")

print(f"Using RAP run: {DATE} {HOUR}Z, F{FCST:02}, Valid {VALID_START}:00-{VALID_END}:00 UTC")

# ================= BUILD URL =================
RAP_URL = f"https://noaa-rap-pds.s3.amazonaws.com/rap.{DATE}/rap.t{HOUR}z.awip32f{FCST:02}.grib2"
print("URL:", RAP_URL)

# ================= DOWNLOAD =================
print("Downloading RAP...")
urllib.request.urlretrieve(RAP_URL, GRIB_PATH)
print("Download complete.")

# ================= OPEN GRIB =================
grbs = pygrib.open(GRIB_PATH)

# ================= PICK VARIABLE =================
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
        print(f"Found {shortname}")
        return g
    raise RuntimeError(f"{shortname} not found")

# ================= LOAD DATA =================
grbs.seek(0)
cape_msg = pick_var(grbs, "cape", typeOfLevel="surface")
grbs.seek(0)
cin_msg = pick_var(grbs, "cin", typeOfLevel="surface")
grbs.seek(0)
hlcy_msg = pick_var(grbs, "hlcy", typeOfLevel="heightAboveGroundLayer", bottom=0, top=1000)

cape = cape_msg.values
cin  = cin_msg.values
hlcy = hlcy_msg.values

# ================= GET LAT/LON =================
lats, lons = cape_msg.latlons()
print("Loaded lat/lon grid")

# ================= BUILD LCC PROJECTION =================
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
print("Initialized LCC projection")

# ================= CONVERT TO X/Y =================
x_vals, y_vals = proj_lcc(lons, lats)
print("Converted to LCC meters")

# ================= CLEAN NaNs =================
cape = np.nan_to_num(cape, nan=0.0)
cin  = np.nan_to_num(cin, nan=0.0)
hlcy = np.nan_to_num(hlcy, nan=0.0)

# ================= PROBABILITY =================
linear = INTERCEPT + COEFFS["CAPE"]*cape + COEFFS["CIN"]*cin + COEFFS["HLCY"]*hlcy
prob = 1 / (1 + np.exp(-linear))

# ================= BUILD FEATURES =================
features = []
rows, cols = prob.shape
print("Grid size:", rows, "x", cols)

for i in range(rows):
    for j in range(cols):
        x = x_vals[i, j]
        y = y_vals[i, j]
        dx = x_vals[i, j+1] - x_vals[i, j] if j < cols-1 else x_vals[i, j] - x_vals[i, j-1]
        dy = y_vals[i+1, j] - y_vals[i, j] if i < rows-1 else y_vals[i, j] - y_vals[i-1, j]
        features.append({
            "x": float(x),
            "y": float(y),
            "dx": float(abs(dx)),
            "dy": float(abs(dy)),
            "prob": float(prob[i,j])
        })

# ================= WRITE JSON =================
output = {
    "run_date": DATE,
    "run_hour": HOUR,
    "forecast": f"F{FCST:02}",
    "valid_start": VALID_START,
    "valid_end": VALID_END,
    "projection": params,
    "features": features
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f)

print("JSON written:", OUTPUT_JSON)
print("Points:", len(features))
print("File size:", os.path.getsize(OUTPUT_JSON), "bytes")
