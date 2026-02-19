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


# ================= PATH SETUP =================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

DATA_DIR = os.path.join(REPO_ROOT, "data")
GRIB_PATH = os.path.join(DATA_DIR, "rap.grib2")

OUTPUT_JSON = os.path.join(
    REPO_ROOT,
    "map",
    "data",
    "tornado_prob_lcc.json"
)

CONUS_PATH = os.path.join(
    REPO_ROOT,
    "map",
    "data",
    "conus_lcc.json"
)


# ================= MODEL =================

INTERCEPT = -14

COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}


os.makedirs(DATA_DIR, exist_ok=True)


# ================= TIME =================

now = datetime.datetime.utcnow() - datetime.timedelta(hours=1)

DATE = now.strftime("%Y%m%d")
HOUR = now.strftime("%H")

URL = f"https://noaa-rap-pds.s3.amazonaws.com/rap.{DATE}/rap.t{HOUR}z.awip32f01.grib2"

print("\nUsing RAP:", DATE, HOUR)


# ================= CHECK =================

if requests.head(URL).status_code != 200:

    print("RAP not ready")
    exit(0)


# ================= DOWNLOAD =================

print("Downloading RAP...")

urllib.request.urlretrieve(URL, GRIB_PATH)

print("Download complete.")


# ================= OPEN GRIB =================

grbs = pygrib.open(GRIB_PATH)


def pick(grbs,name,level=None,bottom=None):

    grbs.seek(0)

    for g in grbs:

        if g.shortName.lower()!=name:
            continue

        if level and g.typeOfLevel!=level:
            continue

        if bottom is not None:

            if not hasattr(g,"bottomLevel"):
                continue

            if abs(g.bottomLevel-bottom)>1:
                continue

        return g

    raise RuntimeError(name+" missing")


cape_msg=pick(grbs,"cape","surface")
cin_msg=pick(grbs,"cin","surface")
hlcy_msg=pick(grbs,"hlcy","heightAboveGroundLayer",0)


cape=cape_msg.values
cin=cin_msg.values
hlcy=hlcy_msg.values


lats,lons=cape_msg.latlons()

params=cape_msg.projparams

proj=Proj(params)

x,y=proj(lons,lats)


# ================= PROBABILITY =================

cape=np.nan_to_num(cape)
cin=np.nan_to_num(cin)
hlcy=np.nan_to_num(hlcy)

linear=INTERCEPT+COEFFS["CAPE"]*cape+COEFFS["CIN"]*cin+COEFFS["HLCY"]*hlcy

prob=1/(1+np.exp(-linear))


# ================= LOAD CONUS =================

print("Loading CONUS border...")

conus=gpd.read_file(CONUS_PATH)

border=conus.geometry.iloc[0]


# ================= FILTER GRID =================

features=[]

rows,cols=prob.shape

count=0

for i in range(rows):
    for j in range(cols):

        pt=Point(x[i,j],y[i,j])

        if not border.intersects(pt):
            continue

        count+=1

        features.append({
            "x":float(x[i,j]),
            "y":float(y[i,j]),
            "prob":float(prob[i,j])
        })


print("Cells inside CONUS:",count)


# ================= SAVE =================

valid_start=f"{HOUR}:00"
valid_end=f"{(int(HOUR)+1)%24:02d}:00"

output={
"run_date":DATE,
"run_hour":HOUR,
"valid":valid_start+"-"+valid_end+" UTC",
"projection":params,
"features":features,
"generated":datetime.datetime.utcnow().isoformat()+"Z"
}

with open(OUTPUT_JSON,"w") as f:
    json.dump(output,f)


print("\nUpdated:",OUTPUT_JSON)
print("SUCCESS\n")
