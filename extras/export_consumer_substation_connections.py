import geopandas as gpd
import pandas as pd

from util import config


def export_consumer_substation_csv(consumers: gpd.GeoDataFrame, substations: gpd.GeoDataFrame):
    cons = consumers.copy()
    subs = substations.copy()

    columns = ["gkz", "name", "lat", "lon", "elwog_plus_id", "substation_name", "substation_lat", "substation_lon"]
    df = pd.DataFrame(columns=columns)  # pyright: ignore[reportArgumentType]
    df["gkz"] = cons.gkz
    df["name"] = cons.name
    df["lat"] = cons.lat.round(5)
    df["lon"] = cons.lon.round(5)

    # Merge consumers and substations
    cons = cons.merge(
        subs[["id", "name", "lat", "lon", "elwog_id"]], left_on="substation_id", right_on="id", how="left"
    )
    cons = cons.rename(
        columns={"name_y": "sub_name", "lat_y": "sub_lat", "lon_y": "sub_lon", "elwog_id": "sub_elwog_id"}
    ).drop(columns="id")

    df["substation_name"] = cons.sub_name
    df["substation_lat"] = cons.sub_lat.round(5)
    df["substation_lon"] = cons.sub_lon.round(5)
    df["elwog_plus_id"] = cons.sub_elwog_id

    # Cleanup df before export
    df.rename(columns=lambda x: " ".join(x.split("_")), inplace=True)
    df.rename(columns=str.title, inplace=True)
    df.rename(columns=lambda x: x.replace("Lat", "Latitude"), inplace=True)
    df.rename(columns=lambda x: x.replace("Lon", "Longitude"), inplace=True)

    destination_dirs = [f"{config.EXPORT_DIR}/extras", "results/extras"]
    for dir in destination_dirs:
        df.to_csv(f"{dir}/sub_con_connections.csv", index=False)
