import geopandas as gpd
import json
import os
from pyproj import CRS
from shapely.validation import make_valid


# ================= PATH SETUP =================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

SHAPEFILE_PATH = os.path.join(
    REPO_ROOT,
    "map",
    "data",
    "ne_50m_admin_1_states_provinces.shp"
)

OUTPUT_PATH = os.path.join(
    REPO_ROOT,
    "map",
    "data",
    "conus_lcc.json"
)

RAP_JSON_PATH = os.path.join(
    REPO_ROOT,
    "map",
    "data",
    "tornado_prob_lcc.json"
)


print("\n=== VERIFYING SHAPEFILE ===")
print("Path:", SHAPEFILE_PATH)

if not os.path.exists(SHAPEFILE_PATH):
    raise RuntimeError("Shapefile NOT FOUND")

print("Shapefile found.")


# ================= LOAD =================

print("\n=== LOADING STATES ===")

states = gpd.read_file(SHAPEFILE_PATH)

print("Total features:", len(states))


# ================= FILTER USA =================

states = states[states["admin"] == "United States of America"]

print("US features:", len(states))


# ================= REMOVE NON-CONUS =================

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

print("CONUS features:", len(states))


# ================= FIX GEOMETRY =================

print("\n=== FIXING GEOMETRY ===")

states["geometry"] = states["geometry"].apply(make_valid)


# ================= DISSOLVE =================

print("\n=== DISSOLVING ===")

conus = states.dissolve()

print("Result type:", conus.geometry.iloc[0].geom_type)


# ================= LOAD RAP PROJECTION =================

print("\n=== LOADING RAP PROJECTION ===")

if not os.path.exists(RAP_JSON_PATH):
    raise RuntimeError("tornado_prob_lcc.json missing")

with open(RAP_JSON_PATH) as f:
    rap = json.load(f)

params = rap["projection"]


# ================= CREATE LCC CRS =================

lcc = CRS.from_proj4(
    f"+proj=lcc "
    f"+lat_1={params['lat_1']} "
    f"+lat_2={params['lat_2']} "
    f"+lat_0={params['lat_0']} "
    f"+lon_0={params['lon_0']} "
    f"+a={params.get('a',6371229)} "
    f"+b={params.get('b',6371229)}"
)


# ================= REPROJECT =================

print("\n=== REPROJECTING ===")

conus = conus.to_crs(lcc)


# ================= SAVE =================

print("\n=== SAVING ===")

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

conus.to_file(OUTPUT_PATH, driver="GeoJSON")

print("Saved:", OUTPUT_PATH)

print("\nSUCCESS\n")
