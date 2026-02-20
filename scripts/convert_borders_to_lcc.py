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

COUNTRIES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"

STATE_LINES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces_lines.zip"


# =============================
# Helper: download shapefile
# =============================

def download_shapefile(url, folder):

    print(f"Downloading {url}")

    resp = requests.get(url)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall(folder)

    shp = [f for f in z.namelist() if f.endswith(".shp")][0]

    return gpd.read_file(f"{folder}/{shp}")


# =============================
# Load datasets
# =============================

countries = download_shapefile(
    COUNTRIES_URL,
    "tmp_countries"
)

state_lines = download_shapefile(
    STATE_LINES_URL,
    "tmp_states"
)


# =============================
# Filter country = USA
# =============================

usa = countries[
    countries["ADMIN"] == "United States of America"
]


# =============================
# Remove Alaska, Hawaii, territories
# via bounding box filter (CONUS)
# =============================

min_lon = -125
max_lon = -66
min_lat = 24
max_lat = 50

usa = usa.cx[min_lon:max_lon, min_lat:max_lat]


# =============================
# Filter state borders to USA only
# =============================

states = state_lines[
    state_lines["adm0_name"] == "United States of America"
]

states = states.cx[min_lon:max_lon, min_lat:max_lat]


# =============================
# Build RAP LCC projection
# =============================

print("Building projection...")

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

usa_lcc = usa.to_crs(lcc_proj)
states_lcc = states.to_crs(lcc_proj)


# =============================
# Convert geometries to lines
# =============================

features = []


# Country outline (exterior only)
for geom in usa_lcc.geometry:

    if geom.geom_type == "MultiPolygon":

        for poly in geom.geoms:

            features.append(
                list(poly.exterior.coords)
            )

    elif geom.geom_type == "Polygon":

        features.append(
            list(geom.exterior.coords)
        )


# State borders (lines)
for geom in states_lcc.geometry:

    if geom.geom_type == "MultiLineString":

        for line in geom.geoms:

            features.append(
                list(line.coords)
            )

    elif geom.geom_type == "LineString":

        features.append(
            list(geom.coords)
        )


# =============================
# Output JSON
# =============================

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


print(f"Saved {len(features)} border lines.")
print("Done.")
