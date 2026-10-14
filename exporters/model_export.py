import json

import geopandas as gpd

from util import config


def export_model(lines: gpd.GeoDataFrame, subs: gpd.GeoDataFrame, gens: gpd.GeoDataFrame):
    destination_dirs = [config.EXPORT_DIR, "results"]

    subs["voltage"] = subs["voltage"].apply(json.dumps)
    subs["export_voltage"] = subs["export_voltage"].apply(lambda x: json.dumps(x) if x is not None else None)

    for dir in destination_dirs:
        lines.to_file(f"{dir}/lines.gpkg", driver="GPKG")
        gens.to_file(f"{dir}/generators.gpkg", driver="GPKG")

        subs.to_file(f"{dir}/substations.gpkg", driver="GPKG")
