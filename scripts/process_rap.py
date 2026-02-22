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

# US Census lower 48 states 5m shapefile
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

# ================= DOWNLOAD RAP =================

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

# ================= DOWNLOAD CONUS SHAPE =================

def download_shapefile(url, folder):
    resp = requests.get(url)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall(folder)
    shp_file = [f for f in z.namelist() if f.endswith(".shp")][0]
    return gpd.read_file(f"{folder}/{shp_file}")

print("Downloading CONUS shapefile...")
states_gdf = download_shapefile(CONUS_SHAPE_URL, "tmp_conus")

# Keep only lower 48 states
lower48 = states_gdf[~states_gdf["STUSPS"].isin(["AK","HI","PR"])]

# Project to RAP LCC
lower48_lcc = lower48.to_crs(proj_lcc.srs)

# Merge into CONUS polygon
conus_poly = lower48_lcc.unary_union
prepared_conus = prep(conus_poly)

# ================= FILTER CELLS =================

print("Filtering grid cells to CONUS (intersects polygon)...")

features = []

rows, cols = cape.shape

for i in range(rows):
    for j in range(cols):

        x = x_vals[i,j]
        y = y_vals[i,j]

        dx = x_vals[i,j+1] - x if j < cols-1 else x - x_vals[i,j-1]
        dy = y_vals[i+1,j] - y if i < rows-1 else y - y_vals[i-1,j]

        dx = abs(dx)
        dy = abs(dy)

        cell_box = box(x, y, x+dx, y+dy)

        if prepared_conus.intersects(cell_box):

            features.append({
                "x": float(x),
                "y": float(y),
                "dx": float(dx),
                "dy": float(dy),

                # OUTPUT RAW VARIABLES INSTEAD OF PROBABILITY
                "cape": float(cape[i,j]),
                "cin": float(cin[i,j]),
                "srh": float(hlcy[i,j])
            })

print(f"Kept {len(features)} cells inside or touching CONUS.")

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

print("Saved:", OUTPUT_JSON)
print("DONE.")
