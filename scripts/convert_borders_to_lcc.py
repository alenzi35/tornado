import geopandas as gpd
import json
import zipfile, io, requests
from shapely.geometry import box, Point
from shapely.ops import unary_union
from pyproj import CRS

# -----------------------------
# Paths
# -----------------------------
CELLS_IN = "map/data/tornado_prob_lcc.json"       # raw RAP cells
CELLS_OUT = "map/data/tornado_prob_lcc_masked.json"  # filtered output
BORDERS_OUT = "map/data/borders_lcc.json"
CENSUS_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"
TMP_DIR = "tmp_census"

# -----------------------------
# Download + unzip Census shapefile
# -----------------------------
print("Downloading US Census lower-48 states shapefile...")
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
# Load RAP cells JSON
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

# Merge into single mainland polygon
mainland_poly = unary_union(gdf_lcc.geometry)

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
# Filter tornado cells to CONUS (centroid must be inside mainland polygon)
# -----------------------------
filtered_cells = []
for c in cells_data["features"]:
    x = c["x"]
    y = c["y"]
    w = c["dx"]
    h = c["dy"]
    centroid = Point(x + w/2, y + h/2)
    if mainland_poly.contains(centroid):
        filtered_cells.append(c)

# -----------------------------
# Save filtered (masked) cells
# -----------------------------
cells_data["features"] = filtered_cells
with open(CELLS_OUT, "w") as f:
    json.dump(cells_data, f)

print(f"Kept {len(filtered_cells)} cells inside mainland CONUS")
print(f"Saved masked cells to {CELLS_OUT}")
print("DONE")
