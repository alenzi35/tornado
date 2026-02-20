#!/usr/bin/env python3

import geopandas as gpd
import requests
import zipfile
import io
import json
import xarray as xr
from pathlib import Path

OUT_PATH = Path("map/data/borders_lcc.json")

URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip"


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


def get_rap_crs():

    ds = xr.open_dataset("map/data/rap_latlon.nc")

    return ds.rio.crs


def main():

    rap_crs = get_rap_crs()

    states = download_shapefile(URL, "tmp_states")

    states = states.to_crs(rap_crs)

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


    print("Borders exported perfectly aligned with RAP grid.")


if __name__ == "__main__":
    main()
