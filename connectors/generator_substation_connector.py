import geopandas as gpd

from util.utils import AUSTRIA_CRS


def connect_generator_to_substation(generators: gpd.GeoDataFrame, substations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gens = generators.copy()
    subs = substations.copy()

    # Create column with dummy value
    gens["substation_id"] = -1

    # find id of closet substation to each generator
    closest_sub_ids = gpd.sjoin_nearest(gens.to_crs(AUSTRIA_CRS), subs.to_crs(AUSTRIA_CRS), how="left").id_right
    gens.loc[closest_sub_ids.index, "substation_id"] = closest_sub_ids.values

    assert all(gens.substation_id != -1)

    return gens
