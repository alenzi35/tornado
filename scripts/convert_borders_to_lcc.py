import geopandas as gpd
import json
import zipfile, io, requests
from shapely.geometry import box, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from pyproj import CRS, Transformer

# -----------------------------
# Paths
# -----------------------------
CELLS_IN = "map/data/tornado_prob_lcc.json"       # raw RAP cells
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
# Filter tornado cells to CONUS (inside or touching polygon)
# -----------------------------
filtered_cells = []
for c in cells_data["features"]:
    x = c["x"]
    y = c["y"]
    w = c["dx"]
    h = c["dy"]
    cell_poly = box(x, y, x+w, y+h)
    if prepared_us.intersects(cell_poly):
        filtered_cells.append(c)

print(f"Kept {len(filtered_cells)} cells touching or inside CONUS polygon")

# -----------------------------
# Remove outlier cells using lat/lon bounds
# -----------------------------
transformer = Transformer.from_crs(rap_crs, "EPSG:4326", always_xy=True)
final_cells = []

for c in filtered_cells:
    x = c["x"] + c["dx"]/2
    y = c["y"] + c["dy"]/2
    lon, lat = transformer.transform(x, y)
    if -125 <= lon <= -65 and 24 <= lat <= 50:  # CONUS bounds
        final_cells.append(c)

cells_data["features"] = final_cells

# -----------------------------
# Write back to JSON
# -----------------------------
with open(CELLS_IN, "w") as f:
    json.dump(cells_data, f)

print(f"Final cell count after CONUS lat/lon filtering: {len(final_cells)}")
print("Done.")
