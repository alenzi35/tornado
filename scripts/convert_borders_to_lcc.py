#!/usr/bin/env python3

import geopandas as gpd
import requests
import zipfile
import io
import json
from pathlib import Path
from pyproj import CRS

OUT_PATH = Path("map/data/borders_lcc.json")

URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"

# EXACT CRS used by RAP grid (official NOAA definition)
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


def main():

    states = download_shapefile(URL, "tmp_states")

    # Project to RAP CRS
    states = states.to_crs(RAP_CRS)

    features = []

    for geom in states.geometry:

        if geom.geom_type == "Polygon":

            features.append(list(geom.exterior.coords))

            for hole in geom.interiors:
                features.append(list(hole.coords))

        elif geom.geom_type == "MultiPolygon":

            for poly in geom.geoms:

                features.append(list(poly.exterior.coords))

                for hole in poly.interiors:
                    features.append(list(hole.coords))


    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_PATH, "w") as f:

        json.dump({
            "features": features
        }, f)


    print("Done. Borders now match RAP projection exactly.")


if __name__ == "__main__":
    main()
