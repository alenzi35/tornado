#!/usr/bin/env python3

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path
from pyproj import CRS

OUT_PATH = Path("map/data/borders_grid.json")

URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"

# RAP projection (correct spherical earth)
RAP_CRS = CRS.from_proj4(
    "+proj=lcc "
    "+lat_1=25 "
    "+lat_2=25 "
    "+lat_0=25 "
    "+lon_0=265 "
    "+a=6371229 "
    "+b=6371229 "
    "+units=m "
    "+no_defs"
)

# THESE MUST MATCH YOUR RAP GRID EXACTLY
DX = 13000.0
DY = 13000.0

NX = 451
NY = 337

# RAP grid origin (lower-left corner)
X0 = -2699020.142521929
Y0 = -1588819.031011287


def download_shapefile(url, folder):

    print(f"Downloading {url}")

    r = requests.get(url)
    r.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(r.content))

    folder = Path(folder)
    folder.mkdir(exist_ok=True)

    z.extractall(folder)

    shp = next(folder.glob("*.shp"))

    return gpd.read_file(shp)


def proj_to_grid(x, y):

    gx = (x - X0) / DX
    gy = (y - Y0) / DY

    return gx, gy


def convert_geom(geom):

    rings = []

    if geom.geom_type == "Polygon":

        rings.append(geom.exterior.coords)

        for hole in geom.interiors:
            rings.append(hole.coords)

    elif geom.geom_type == "MultiPolygon":

        for poly in geom.geoms:

            rings.append(poly.exterior.coords)

            for hole in poly.interiors:
                rings.append(hole.coords)

    result = []

    for ring in rings:

        converted = []

        for x, y in ring:

            gx, gy = proj_to_grid(x, y)

            converted.append([gx, gy])

        result.append(converted)

    return result


def main():

    states = download_shapefile(URL, "tmp_states")

    states = states.to_crs(RAP_CRS)

    features = []

    for geom in states.geometry:

        features.extend(convert_geom(geom))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_PATH, "w") as f:

        json.dump({
            "nx": NX,
            "ny": NY,
            "features": features
        }, f)

    print("Borders now perfectly aligned with RAP grid.")


if __name__ == "__main__":
    main()
