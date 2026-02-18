import geopandas as gpd
import json
import os
from pyproj import CRS


# ================= CONFIG =================

SHAPEFILE_PATH = "data/shapefiles/ne_10m_admin_1_states_provinces_lakes.shp"
OUTPUT_PATH = "map/data/conus_lcc.json"


print("\n=== LOADING STATES SHAPEFILE ===")

states = gpd.read_file(SHAPEFILE_PATH)

print("Total features loaded:", len(states))


# ================= FILTER TO USA ONLY =================

states = states[states["admin"] == "United States of America"]

print("US states count:", len(states))


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

print("CONUS states count:", len(states))


# ================= DISSOLVE TO SINGLE POLYGON =================

print("\n=== DISSOLVING TO CONUS POLYGON ===")

conus = states.dissolve()

print("Dissolved geometry type:", conus.geometry.iloc[0].geom_type)


# ================= LOAD PROJECTION FROM RAP OUTPUT =================

print("\n=== MATCHING RAP PROJECTION ===")

with open("map/data/tornado_prob_lcc.json") as f:
    rap_data = json.load(f)

proj_params = rap_data["projection"]

lcc_crs = CRS.from_proj4(
    f"+proj=lcc "
    f"+lat_1={proj_params['lat_1']} "
    f"+lat_2={proj_params['lat_2']} "
    f"+lat_0={proj_params['lat_0']} "
    f"+lon_0={proj_params['lon_0']} "
    f"+a={proj_params.get('a', 6371229)} "
    f"+b={proj_params.get('b', 6371229)}"
)

conus = conus.to_crs(lcc_crs)

print("Reprojection complete.")


# ================= EXPORT GEOJSON =================

print("\n=== EXPORTING CONUS LCC OUTLINE ===")

os.makedirs("map/data", exist_ok=True)

conus.to_file(OUTPUT_PATH, driver="GeoJSON")

print("Saved to:", OUTPUT_PATH)
print("Done.\n")
