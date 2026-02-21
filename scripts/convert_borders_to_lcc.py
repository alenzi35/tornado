import json
import zipfile
import io
import requests

import geopandas as gpd
import xarray as xr

from shapely.geometry import box, Point
from shapely.ops import unary_union

from pyproj import CRS, Transformer, Proj


# =====================================================
# CONFIG
# =====================================================

US_STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip"

INPUT_CELLS = "map/data/tornado_prob_lcc.json"

OUTPUT_BORDERS = "map/data/us_borders_lcc.json"
OUTPUT_CELLS = "map/data/tornado_prob_lcc_filtered.json"

RAP_FILE = "map/data/rap_latlon.nc"

DALLAS_LAT = 32.7767
DALLAS_LON = -96.7970


# =====================================================
# DOWNLOAD + LOAD SHAPEFILE
# =====================================================

def download_shapefile(url):
    print(f"Downloading {url}")

    resp = requests.get(url)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))

    z.extractall("tmp_us_states")

    shp = [f for f in z.namelist() if f.endswith(".shp")][0]

    return gpd.read_file(f"tmp_us_states/{shp}")


# =====================================================
# GET RAP CRS
# =====================================================

def get_rap_crs():

    ds = xr.open_dataset(RAP_FILE)

    proj = ds["LambertConformal_Projection"]

    crs = CRS.from_proj4(
        f"+proj=lcc "
        f"+lat_1={proj.standard_parallel.values[0]} "
        f"+lat_2={proj.standard_parallel.values[1]} "
        f"+lat_0={proj.latitude_of_projection_origin.values} "
        f"+lon_0={proj.longitude_of_central_meridian.values} "
        f"+a=6371229 +b=6371229"
    )

    print("RAP CRS loaded")

    return crs


# =====================================================
# CONVERT GEOMETRY TO LCC
# =====================================================

def convert_to_lcc(gdf, rap_crs):

    transformer = Transformer.from_crs(
        "EPSG:4326",
        rap_crs,
        always_xy=True
    )

    gdf = gdf.to_crs(rap_crs)

    return gdf


# =====================================================
# LOAD CELLS
# =====================================================

def load_cells():

    with open(INPUT_CELLS) as f:
        data = json.load(f)

    return data["features"]


# =====================================================
# FILTER CELLS BY US GEOMETRY
# =====================================================

def filter_cells(cells, us_geom):

    filtered = []

    for c in cells:

        dx = c.get("dx", 13545)
        dy = c.get("dy", 13545)

        poly = box(
            c["x"],
            c["y"],
            c["x"] + dx,
            c["y"] + dy
        )

        if poly.intersects(us_geom):
            filtered.append(c)

    print(f"Cells before: {len(cells)}")
    print(f"Cells after: {len(filtered)}")

    return filtered


# =====================================================
# FIND DALLAS CELL
# =====================================================

def highlight_dallas(cells, rap_crs):

    proj = Proj(rap_crs)

    lon360 = DALLAS_LON if DALLAS_LON >= 0 else 360 + DALLAS_LON

    x, y = proj(lon360, DALLAS_LAT)

    print(f"Dallas projected: x={x:.2f}, y={y:.2f}")

    closest = None
    closest_dist = 1e30

    for c in cells:

        dx = c.get("dx", 13545)
        dy = c.get("dy", 13545)

        cx = c["x"] + dx / 2
        cy = c["y"] + dy / 2

        dist = (cx - x)**2 + (cy - y)**2

        if dist < closest_dist:
            closest_dist = dist
            closest = c

    for c in cells:
        c["highlight"] = False

    if closest:
        closest["highlight"] = True
        print(
            f'Dallas cell: x={closest["x"]}, y={closest["y"]}'
        )

    return cells


# =====================================================
# SAVE GEOJSON
# =====================================================

def save_borders(gdf):

    geojson = json.loads(gdf.to_json())

    with open(OUTPUT_BORDERS, "w") as f:
        json.dump(geojson, f)

    print("Saved borders")


def save_cells(cells):

    geojson = {
        "type": "FeatureCollection",
        "features": cells
    }

    with open(OUTPUT_CELLS, "w") as f:
        json.dump(geojson, f)

    print("Saved filtered cells")


# =====================================================
# MAIN
# =====================================================

def main():

    rap_crs = get_rap_crs()

    states = download_shapefile(US_STATES_URL)

    # remove Alaska, Hawaii, territories
    states = states[
        ~states["STUSPS"].isin(
            ["AK", "HI", "PR", "GU", "VI", "MP", "AS"]
        )
    ]

    states_lcc = convert_to_lcc(states, rap_crs)

    us_geom = unary_union(states_lcc.geometry)

    save_borders(states_lcc)

    cells = load_cells()

    cells = filter_cells(cells, us_geom)

    cells = highlight_dallas(cells, rap_crs)

    save_cells(cells)


if __name__ == "__main__":
    main()
