import geopandas as gpd
import requests
import zipfile
import io
import json
from pyproj import CRS
from shapely.geometry import Polygon, box
import os

# -----------------------------
# Paths
# -----------------------------
OUT_BORDER_PATH = "map/data/borders_lcc.json"
OUT_CELL_PATH = "map/data/tornado_prob_lcc.json"

NE_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces.zip"
TORNADO_JSON = "map/data/tornado_prob_lcc.json"  # existing tornado JSON

os.makedirs("tmp_borders", exist_ok=True)
os.makedirs("map/data", exist_ok=True)

# -----------------------------
# Download + unzip shapefile
# -----------------------------
print("Downloading Natural Earth borders...")
resp = requests.get(NE_URL)
resp.raise_for_status()
z = zipfile.ZipFile(io.BytesIO(resp.content))
z.extractall("tmp_borders")
print("Download complete.")

# -----------------------------
# Load shapefile
# -----------------------------
shp_path = "tmp_borders/ne_50m_admin_1_states_provinces.shp"
print("Loading shapefile...")
gdf = gpd.read_file(shp_path)

# -----------------------------
# Filter to USA CONUS only
# -----------------------------
CONUS_STATES = [
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

gdf = gdf[gdf["admin"] == "United States of America"]
gdf = gdf[gdf["name"].isin(CONUS_STATES)]

# -----------------------------
# Build LCC projection
# -----------------------------
print("Building LCC projection...")
lcc_proj = CRS.from_proj4(
    "+proj=lcc "
    "+lat_1=50 "
    "+lat_2=50 "
    "+lat_0=50 "
    "+lon_0=253 "
    "+a=6371229 "
    "+b=6371229 "
    "+units=m "
    "+no_defs"
)

# -----------------------------
# Reproject
# -----------------------------
print("Reprojecting borders...")
gdf_lcc = gdf.to_crs(lcc_proj)

# -----------------------------
# Export borders to JSON
# -----------------------------
features = []
for geom in gdf_lcc.geometry:
    if geom is None:
        continue
    if geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            coords = list(poly.exterior.coords)
            features.append(coords)
    elif geom.geom_type == "Polygon":
        coords = list(geom.exterior.coords)
        features.append(coords)

out_borders = {
    "projection": {
        "proj": "lcc",
        "lat_0": 50,
        "lat_1": 50,
        "lat_2": 50,
        "lon_0": 253,
        "a": 6371229,
        "b": 6371229
    },
    "features": features
}

with open(OUT_BORDER_PATH, "w") as f:
    json.dump(out_borders, f)
print(f"Saved {len(features)} CONUS borders to {OUT_BORDER_PATH}")

# -----------------------------
# Filter tornado cells to CONUS
# -----------------------------
if os.path.exists(TORNADO_JSON):
    print("Filtering tornado cells to CONUS...")
    with open(TORNADO_JSON) as f:
        cells = json.load(f)["features"]

    # Merge CONUS polygons into single Shapely polygon
    conus_polygon = gdf_lcc.unary_union

    filtered_cells = []
    for c in cells:
        cell_box = box(c['x'], c['y'], c['x'] + c['dx'], c['y'] + c['dy'])
        if cell_box.intersects(conus_polygon):
            filtered_cells.append(c)

    # Export filtered tornado cells
    output = {
        "projection": out_borders["projection"],
        "features": filtered_cells
    }

    with open(OUT_CELL_PATH, "w") as f:
        json.dump(output, f)

    print(f"Saved {len(filtered_cells)} CONUS tornado cells to {OUT_CELL_PATH}")
else:
    print("No tornado_prob_lcc.json found yet. Skipping cell filtering.")

print("Done.")
