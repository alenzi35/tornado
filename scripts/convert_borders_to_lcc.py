import geopandas as gpd
import json
import zipfile, io, requests
from shapely.geometry import box
from shapely.ops import unary_union
from shapely.prepared import prep
from pyproj import CRS

# -----------------------------
# Paths
# -----------------------------
CELLS_IN = "map/data/tornado_prob_lcc.json"
BORDERS_OUT = "map/data/borders_lcc.json"
CENSUS_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"
TMP_DIR = "tmp_census"

# -----------------------------
# Download + unzip Census shapefile
# -----------------------------
resp = requests.get(CENSUS_URL)
resp.raise_for_status()
z = zipfile.ZipFile(io.BytesIO(resp.content))
z.extractall(TMP_DIR)
shp_path = f"{TMP_DIR}/cb_2024_us_state_5m.shp"
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
# Build RAP CRS
# -----------------------------
with open(CELLS_IN) as f:
    cells_data = json.load(f)

p = cells_data["projection"]
rap_crs = CRS.from_proj4(
    f"+proj=lcc +lat_1={p['lat_1']} +lat_2={p['lat_2']} +lat_0={p['lat_0']} "
    f"+lon_0={p['lon_0']} +a={p.get('a',6371229)} +b={p.get('b',6371229)} +units=m +no_defs"
)

# -----------------------------
# Reproject borders
# -----------------------------
gdf_lcc = gdf.to_crs(rap_crs)
us_poly = unary_union(gdf_lcc.geometry)
prepared_us = prep(us_poly)

# -----------------------------
# Export lower-48 borders
# -----------------------------
features = []
for geom in gdf_lcc.geometry:
    if geom.geom_type == "Polygon":
        features.append(list(geom.exterior.coords))
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            features.append(list(poly.exterior.coords))
with open(BORDERS_OUT, "w") as f:
    json.dump({"features": features}, f)
print(f"Saved {len(features)} lower-48 borders to {BORDERS_OUT}")

# -----------------------------
# Filter tornado cells to CONUS polygon (inside or touching)
# -----------------------------
filtered_cells = []
for c in cells_data["features"]:
    x = c["x"]
    y = c["y"]
    w = c["dx"]
    h = c["dy"]
    cell_poly = box(x, y, x+w, y+h)
    # keep only cells that touch the prepared CONUS polygon
    if prepared_us.intersects(cell_poly):
        filtered_cells.append(c)

print(f"Cells touching or inside CONUS polygon: {len(filtered_cells)}")

# -----------------------------
# Write filtered cells back to JSON
# -----------------------------
cells_data["features"] = filtered_cells
with open(CELLS_IN, "w") as f:
    json.dump(cells_data, f)

print(f"Final cell count written to {CELLS_IN}")
print("Done.")
