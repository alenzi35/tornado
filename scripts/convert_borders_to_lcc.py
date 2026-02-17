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

NE_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces.zip"


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
# Filter to USA only
# -----------------------------

print("Filtering to USA...")

gdf = gdf[gdf["admin"] == "United States of America"]


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
