import geopandas as gpd
import requests
import zipfile
import io
import json
from pyproj import CRS

# -----------------------------
# Paths
# -----------------------------
OUT_PATH = "map/data/borders_lcc.json"
CENSUS_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"
TMP_DIR = "tmp_census"

# -----------------------------
# Download + unzip shapefile
# -----------------------------
print("Downloading US Census Cartographic Boundary states (5m)...")
resp = requests.get(CENSUS_URL)
resp.raise_for_status()

z = zipfile.ZipFile(io.BytesIO(resp.content))
z.extractall(TMP_DIR)
print("Download complete.")

# -----------------------------
# Load shapefile
# -----------------------------
shp_path = f"{TMP_DIR}/cb_2024_us_state_5m.shp"
print("Loading shapefile...")
gdf = gpd.read_file(shp_path)

# -----------------------------
# Filter to lower 48 states
# -----------------------------
lower48 = [
    'AL','AZ','AR','CA','CO','CT','DE','FL','GA','ID','IL','IN','IA','KS','KY','LA',
    'ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND',
    'OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'
]

gdf = gdf[gdf['STUSPS'].isin(lower48)]

# -----------------------------
# Build RAP LCC projection
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
print("Reprojecting...")
gdf_lcc = gdf.to_crs(lcc_proj)

# -----------------------------
# Export to JSON
# -----------------------------
print("Exporting JSON...")
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

out = {
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

with open(OUT_PATH, "w") as f:
    json.dump(out, f)

print(f"Saved {len(features)} borders to {OUT_PATH}")
print("Done.")
