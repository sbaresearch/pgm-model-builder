import geopandas as gpd

from util import config


def load_generators() -> gpd.GeoDataFrame:
    generators = _get_generators_from_csv()

    return generators


def _get_generators_from_csv() -> gpd.GeoDataFrame:
    gens_gdf = gpd.read_file(f"{config.MODEL_PATH}/generators.gpkg")

    return gens_gdf
