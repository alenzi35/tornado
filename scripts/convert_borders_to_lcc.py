import geopandas as gpd
import json
import os
from pyproj import CRS
from shapely.geometry import box


# ================= CONFIG =================

SHAPEFILE_PATH = "map/data/ne_50m_admin_1_states_provinces.shp"
OUTPUT_PATH = "map/data/conus_lcc.json"

RAP_JSON = "map/data/tornado_prob_lcc.json"


# ================= LOAD STATES =================

print("\n=== LOADING STATES SHAPEFILE ===")

states = gpd.read_file(SHAPEFILE_PATH)

print("Loaded features:", len(states))


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

print("After exclusion:", len(states))


# ================= FIX INVALID GEOMETRY =================

print("\n=== FIXING GEOMETRY ===")

states["geometry"] = states["geometry"].buffer(0)

print("Geometry fixed.")


# ================= DISSOLVE INTO SINGLE CONUS =================

print("\n=== DISSOLVING STATES ===")

conus = states.dissolve()

print("Dissolved.")


# ================= HARD CLIP TO CONUS BOUNDING BOX =================

print("\n=== CLIPPING TO CONUS BOUNDS ===")

# lat/lon bounding box for continental US
bbox = box(-125, 24, -66.5, 50)

# ensure CRS is WGS84 first
conus = conus.to_crs(epsg=4326)

conus["geometry"] = conus["geometry"].intersection(bbox)

print("Clipped.")


# ================= LOAD RAP PROJECTION =================

print("\n=== LOADING RAP PROJECTION ===")

with open(RAP_JSON) as f:
    rap = json.load(f)

params = rap["projection"]


lcc = CRS.from_proj4(
    f"+proj=lcc "
    f"+lat_1={params['lat_1']} "
    f"+lat_2={params['lat_2']} "
    f"+lat_0={params['lat_0']} "
    f"+lon_0={params['lon_0']} "
    f"+a={params.get('a', 6371229)} "
    f"+b={params.get('b', 6371229)}"
)


# ================= REPROJECT =================

print("\n=== REPROJECTING TO LCC ===")

conus = conus.to_crs(lcc)

print("Reprojected.")


# ================= SAVE =================

print("\n=== SAVING ===")

os.makedirs("map/data", exist_ok=True)

conus.to_file(
    OUTPUT_PATH,
    driver="GeoJSON"
)

print("Saved:", OUTPUT_PATH)
print("\nSUCCESS\n")
