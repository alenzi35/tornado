import geopandas as gpd
import requests
import zipfile
import io
import json
import math
from pyproj import CRS, Transformer
from shapely.geometry import shape, box, Point
from shapely.ops import unary_union


# ============================================================
# CONFIG
# ============================================================

BORDERS_OUT = "map/data/borders_lcc.json"
CELLS_IN = "map/data/tornado_prob_lcc.json"
CELLS_OUT = "map/data/tornado_prob_lcc_masked.json"

# US Census states (correct lakes, no Michigan absorption)
CENSUS_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip"

DALLAS_LAT = 32.7767
DALLAS_LON = -96.7970


# ============================================================
# LOAD RAP CRS
# ============================================================

def get_rap_crs():

    print("Loading RAP CRS from tornado_prob_lcc.json")

    with open(CELLS_IN) as f:
        data = json.load(f)

    p = data["projection"]

    crs = CRS.from_proj4(
        f"+proj=lcc "
        f"+lat_1={p['lat_1']} "
        f"+lat_2={p['lat_2']} "
        f"+lat_0={p['lat_0']} "
        f"+lon_0={p['lon_0']} "
        f"+a={p.get('a',6371229)} "
        f"+b={p.get('b',6371229)} "
        f"+units=m +no_defs"
    )

    print("RAP CRS loaded")

    return crs


# ============================================================
# DOWNLOAD CENSUS STATES
# ============================================================

def download_states():

    print("Downloading Census states shapefile...")

    resp = requests.get(CENSUS_URL)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall("tmp_states")

    shp = "tmp_states/cb_2023_us_state_20m.shp"

    gdf = gpd.read_file(shp)

    print("States loaded:", len(gdf))

    return gdf


# ============================================================
# BUILD US POLYGON
# ============================================================

def build_us_polygon(gdf, rap_crs):

    print("Reprojecting states to RAP CRS...")

    gdf = gdf.to_crs(rap_crs)

    print("Building unified US polygon...")

    us_poly = unary_union(gdf.geometry)

    return us_poly, gdf


# ============================================================
# EXPORT BORDERS
# ============================================================

def export_borders(gdf):

    features = []

    for geom in gdf.geometry:

        if geom.geom_type == "Polygon":

            coords = list(geom.exterior.coords)
            features.append(coords)

        elif geom.geom_type == "MultiPolygon":

            for poly in geom.geoms:
                coords = list(poly.exterior.coords)
                features.append(coords)

    out = {
        "features": features
    }

    with open(BORDERS_OUT, "w") as f:
        json.dump(out, f)

    print("Saved borders:", len(features))


# ============================================================
# FILTER CELLS BY OUTLINE
# ============================================================

def filter_cells(us_poly):

    print("Loading cells...")

    with open(CELLS_IN) as f:
        data = json.load(f)

    cells = data["features"]

    print("Cells before:", len(cells))

    filtered = []

    dallas_cell = None
    best_dist = 1e30

    transformer = Transformer.from_crs("EPSG:4326", get_rap_crs(), always_xy=True)

    dx, dy = transformer.transform(DALLAS_LON, DALLAS_LAT)

    print("Dallas projected:", dx, dy)

    for c in cells:

        x = c["x"]
        y = c["y"]
        w = c["dx"]
        h = c["dy"]

        cell_poly = box(x, y, x+w, y+h)

        if cell_poly.intersects(us_poly):

            c["inside"] = True
            filtered.append(c)

            cx = x + w/2
            cy = y + h/2

            dist = math.hypot(cx - dx, cy - dy)

            if dist < best_dist:
                best_dist = dist
                dallas_cell = c

    print("Cells after:", len(filtered))

    if dallas_cell:
        dallas_cell["dallas"] = True
        print("Dallas cell:", dallas_cell["x"], dallas_cell["y"])

    data["features"] = filtered

    with open(CELLS_OUT, "w") as f:
        json.dump(data, f)

    print("Saved masked cells")


# ============================================================
# MAIN
# ============================================================

def main():

    rap_crs = get_rap_crs()

    states = download_states()

    us_poly, states_lcc = build_us_polygon(states, rap_crs)

    export_borders(states_lcc)

    filter_cells(us_poly)

    print("DONE")


if __name__ == "__main__":
    main()
