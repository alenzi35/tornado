import geopandas as gpd
import requests
import zipfile
import io
import json
import math
from shapely.geometry import box, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from pyproj import CRS, Transformer

# ============================================================
# CONFIG
# ============================================================

BORDERS_OUT = "map/data/borders_lcc.json"
CELLS_IN = "map/data/tornado_prob_lcc.json"
CELLS_OUT = "map/data/tornado_prob_lcc_masked.json"

# US Census states (correct lakes, no Michigan absorption)
CENSUS_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"


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

    shp_file = [f for f in z.namelist() if f.endswith(".shp")][0]
    gdf = gpd.read_file(f"tmp_states/{shp_file}")

    print("States loaded:", len(gdf))
    return gdf


# ============================================================
# BUILD CONUS POLYGON
# ============================================================

def build_conus_polygon(gdf, rap_crs):
    print("Filtering to CONUS (lower 48)...")
    lower48_states = [
        "Alabama","Arizona","Arkansas","California","Colorado","Connecticut",
        "Delaware","Florida","Georgia","Idaho","Illinois","Indiana","Iowa",
        "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts",
        "Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska",
        "Nevada","New Hampshire","New Jersey","New Mexico","New York",
        "North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania",
        "Rhode Island","South Carolina","South Dakota","Tennessee","Texas",
        "Utah","Vermont","Virginia","Washington","West Virginia","Wisconsin",
        "Wyoming"
    ]
    gdf = gdf[gdf["NAME"].isin(lower48_states)]

    # Reproject to RAP LCC
    gdf = gdf.to_crs(rap_crs)

    # Merge to single polygon
    conus_poly = unary_union(gdf.geometry)
    prepared_conus = prep(conus_poly)

    print("CONUS polygon ready.")
    return conus_poly, prepared_conus, gdf


# ============================================================
# EXPORT BORDERS
# ============================================================

def export_borders(gdf):
    features = []
    for geom in gdf.geometry:
        if geom.geom_type == "Polygon":
            features.append(list(geom.exterior.coords))
        elif geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                features.append(list(poly.exterior.coords))

    out = {"features": features}
    with open(BORDERS_OUT, "w") as f:
        json.dump(out, f)

    print("Saved borders:", len(features))


# ============================================================
# FILTER CELLS BY CONUS
# ============================================================

def filter_cells(prepared_conus):
    print("Loading cells...")
    with open(CELLS_IN) as f:
        data = json.load(f)

    cells = data["features"]
    print("Cells before filtering:", len(cells))

    filtered = []
    for c in cells:
        cx = c["x"] + c["dx"]/2
        cy = c["y"] + c["dy"]/2
        pt = Point(cx, cy)

        if prepared_conus.contains(pt):
            filtered.append(c)

    print("Cells after filtering:", len(filtered))

    data["features"] = filtered
    with open(CELLS_OUT, "w") as f:
        json.dump(data, f)

    print("Saved CONUS-only cells:", CELLS_OUT)


# ============================================================
# MAIN
# ============================================================

def main():
    rap_crs = get_rap_crs()
    states = download_states()
    conus_poly, prepared_conus, states_lcc = build_conus_polygon(states, rap_crs)
    export_borders(states_lcc)
    filter_cells(prepared_conus)
    print("DONE")


if __name__ == "__main__":
    main()
