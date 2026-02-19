import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
import requests
import geopandas as gpd

from shapely.geometry import Point
from pyproj import Proj


# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"

OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

CONUS_SHP = "data/shapefiles/ne_50m_admin_1_states_provinces_lakes.shp"

INTERCEPT = -14

COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs("map/data", exist_ok=True)


# ================= GET LATEST AVAILABLE RAP =================

def get_latest_cycle():

    now = datetime.datetime.utcnow()

    for offset in range(0, 6):

        test = now - datetime.timedelta(hours=offset)

        date = test.strftime("%Y%m%d")
        hour = test.strftime("%H")

        url = (
            f"https://noaa-rap-pds.s3.amazonaws.com/"
            f"rap.{date}/rap.t{hour}z.awip32f01.grib2"
        )

        try:

            r = requests.head(url, timeout=10)

            if r.status_code == 200:

                print("Using RAP:", date, hour)

                return date, hour, url

        except:
            pass

    raise RuntimeError("No RAP cycle found")


DATE, HOUR, RAP_URL = get_latest_cycle()


# ================= DOWNLOAD =================

print("Downloading RAP...")

urllib.request.urlretrieve(RAP_URL, GRIB_PATH)

print("Download complete.")


# ================= LOAD GRIB =================

print("Opening GRIB...")

grbs = pygrib.open(GRIB_PATH)


def pick_var(grbs, shortname, level_type=None, bottom=None, top=None):

    grbs.seek(0)

    for g in grbs:

        if g.shortName.lower() != shortname.lower():
            continue

        if level_type and g.typeOfLevel != level_type:
            continue

        if bottom is not None and top is not None:

            if not hasattr(g, "bottomLevel"):
                continue

            if not (
                abs(g.bottomLevel - bottom) < 1 and
                abs(g.topLevel - top) < 1
            ):
                continue

        return g

    raise RuntimeError(f"{shortname} not found")


print("Selecting variables...")

cape_msg = pick_var(grbs, "cape", "surface")

cin_msg = pick_var(grbs, "cin", "surface")

hlcy_msg = pick_var(
    grbs,
    "hlcy",
    "heightAboveGroundLayer",
    0,
    1000
)


cape = np.nan_to_num(cape_msg.values)
cin = np.nan_to_num(cin_msg.values)
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


# ================= LOAD CONUS =================

print("Loading CONUS shapefile...")

states = gpd.read_file(CONUS_SHP)

states = states[states["admin"] == "United States of America"]

exclude = [
    "Alaska",
    "Hawaii",
    "Puerto Rico",
    "Guam",
    "American Samoa",
    "Northern Mariana Islands",
    "United States Virgin Islands"
]

states = states[~states["name"].isin(exclude)]

states = states.to_crs(params)

conus_geom = states.geometry.buffer(0).union_all()

print("CONUS loaded.")


# ================= COMPUTE PROBABILITY =================

linear = (
    INTERCEPT +
    COEFFS["CAPE"] * cape +
    COEFFS["CIN"] * cin +
    COEFFS["HLCY"] * hlcy
)

prob = 1 / (1 + np.exp(-linear))


# ================= BUILD FEATURES =================

print("Building features...")

features = []

rows, cols = prob.shape

count_total = 0
count_kept = 0

for i in range(rows):

    for j in range(cols):

        count_total += 1

        x = x_vals[i, j]
        y = y_vals[i, j]

        pt = Point(x, y)

        if not conus_geom.contains(pt):
            continue

        count_kept += 1

        dx = x_vals[i, j+1] - x if j < cols-1 else x - x_vals[i, j-1]
        dy = y_vals[i+1, j] - y if i < rows-1 else y - y_vals[i-1, j]

        features.append({

            "x": float(x),
            "y": float(y),
            "dx": float(abs(dx)),
            "dy": float(abs(dy)),
            "prob": float(prob[i, j])

        })


print("Total cells:", count_total)
print("CONUS cells:", count_kept)


# ================= SAVE OUTPUT =================

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
