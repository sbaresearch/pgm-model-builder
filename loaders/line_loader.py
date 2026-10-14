import geopandas as gpd

from util import config


def load_lines() -> gpd.GeoDataFrame:
    return _get_lines_from_file()


def _get_lines_from_file() -> gpd.GeoDataFrame:
    lines_gdf = gpd.read_file(f"{config.MODEL_PATH}/lines.gpkg")

    # NAs can get turned into a string "<NA>" when saving a geopkg
    lines_gdf.loc[lines_gdf[lines_gdf.circuits == "<NA>"].index, "circuits"] = None
    lines_gdf = lines_gdf.astype({"circuits": "Int8"})

    return lines_gdf
