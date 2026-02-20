import geopandas as gpd
import requests
import zipfile
import io
import json
from pyproj import CRS


# =============================
# Paths
# =============================

OUT_PATH = "map/data/borders_lcc.json"

LAND_URL = "https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_land.zip"


# =============================
# Download + unzip shapefile
# =============================

print("Downloading Natural Earth land polygons...")

resp = requests.get(LAND_URL)
resp.raise_for_status()

z = zipfile.ZipFile(io.BytesIO(resp.content))
z.extractall("tmp_land")

print("Download complete.")


# =============================
# Load shapefile
# =============================

shp_path = "tmp_land/ne_50m_land.shp"

print("Loading shapefile...")

gdf = gpd.read_file(shp_path)


# =============================
# Optional: Filter roughly to North America / CONUS region
# (reduces file size, speeds rendering)
# =============================

print("Filtering to CONUS region...")

# Bounding box in lat/lon
min_lon = -130
max_lon = -60
min_lat = 20
max_lat = 55

gdf = gdf.cx[min_lon:max_lon, min_lat:max_lat]


# =============================
# Build RAP LCC projection
# =============================

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


# =============================
# Reproject
# =============================

print("Reprojecting...")

gdf_lcc = gdf.to_crs(lcc_proj)


# =============================
# Export to JSON
# =============================

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


print(f"Saved {len(features)} land border polygons to {OUT_PATH}")
print("Done.")
