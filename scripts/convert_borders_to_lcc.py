import geopandas as gpd
import requests
import zipfile
import io
import json
from shapely.ops import unary_union
from pyproj import CRS, Transformer
from shapely.geometry import shape, box

# ================= CONFIG =================

BORDERS_OUT = "map/data/borders_lcc.json"
CELLS_IN = "map/data/tornado_prob_lcc.json"

# Use 2024 US Census 5m shapefile
CENSUS_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"

# ================= LOAD RAP CRS =================

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

# ================= DOWNLOAD STATES =================

def download_states():
    print("Downloading Census states shapefile...")
    resp = requests.get(CENSUS_URL)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall("tmp_states")
    shp = [f for f in z.namelist() if f.endswith(".shp")][0]
    gdf = gpd.read_file(f"tmp_states/{shp}")
    print("States loaded:", len(gdf))
    return gdf

# ================= BUILD CONUS POLYGON =================

def build_conus_polygon(gdf, rap_crs):
    # Keep only lower 48 states (exclude Alaska=2, Hawaii=15, Puerto Rico=72)
    lower48 = gdf[~gdf["STATEFP"].isin(["02","15","72"])].copy()
    print("Lower 48 states:", len(lower48))

    # Reproject to RAP LCC CRS
    lower48 = lower48.to_crs(rap_crs)
    conus_poly = unary_union(lower48.geometry)
    return conus_poly, lower48

# ================= EXPORT BORDERS =================

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
    out = {"features": features}
    with open(BORDERS_OUT, "w") as f:
        json.dump(out, f)
    print("Saved borders:", len(features))

# ================= FILTER CELLS =================

def filter_cells(conus_poly):
    print("Loading tornado cells...")
    with open(CELLS_IN) as f:
        data = json.load(f)
    cells = data["features"]
    print("Cells before filtering:", len(cells))

    filtered = []
    for c in cells:
        x = c["x"]
        y = c["y"]
        w = c["dx"]
        h = c["dy"]
        cell_poly = box(x, y, x+w, y+h)
        if cell_poly.intersects(conus_poly):
            filtered.append(c)

    data["features"] = filtered

    with open(CELLS_IN, "w") as f:
        json.dump(data, f)

    print("Cells after filtering:", len(filtered))

# ================= MAIN =================

def main():
    rap_crs = get_rap_crs()
    states = download_states()
    conus_poly, states_lcc = build_conus_polygon(states, rap_crs)
    export_borders(states_lcc)
    filter_cells(conus_poly)
    print("DONE")

if __name__ == "__main__":
    main()
