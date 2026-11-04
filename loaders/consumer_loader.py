import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from util.utils import CRS


def load_consumers() -> gpd.GeoDataFrame:
    consumers = _get_consumers_from_csv()

    return consumers


def _get_consumers_from_csv() -> gpd.GeoDataFrame:
    consumers = pd.read_csv(
        "data/consumers/community_coord_boku.csv",
        sep=";",
        decimal=",",
        dtype={
            "Lat0": float,
            "Lon0": float,
        },
    )
    consumers.rename(columns={"GdeCode": "gkz", "Lat0": "lat", "Lon0": "lon", "GdeAmt": "name"}, inplace=True)
    consumers["name"] = consumers.name.apply(lambda n: n.removeprefix("GdeAmt_"))
    consumers["point"] = list(map(Point, zip(consumers.lon, consumers.lat)))  # type: ignore

    consumers = gpd.GeoDataFrame(consumers, geometry="point", crs=CRS)

    return consumers
