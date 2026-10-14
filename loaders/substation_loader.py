import json

import geopandas as gpd
import pandas as pd
from shapely import Point

from util import config
from util.utils import AUSTRIA_CRS, CRS, vprint


def load_substations() -> gpd.GeoDataFrame:
    return _get_substations_from_file()


def _get_substations_from_file() -> gpd.GeoDataFrame:
    subs_gdf = gpd.read_file(f"{config.MODEL_PATH}/substations.gpkg")
    subs_gdf["voltage"] = subs_gdf["voltage"].apply(json.loads)

    return subs_gdf


def merge_consumer_substations(subs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Finds the closest real substation to each substation in the ELWOG csv.
    Marks these substations as 'consumer_substation', or 'virtual_consumer_substation'."""
    subs = subs.copy()

    # Load ELWOG Substations
    elwog_subs = pd.read_csv("data/substations/ELWOG_plus-Datensatz_USPW.csv", sep=";")
    elwog_subs = elwog_subs.rename(columns=str.lower).rename(
        columns={
            "latitude (y)": "lat",
            "longitude (x)": "lon",
            "uspw-id": "elwog_id",
            "uspw-name": "name",
            "typ": "status",
            "betrieb_2022": "in_service",
        }
    )
    elwog_subs["elwog_id"] = elwog_subs.elwog_id.astype(int)
    elwog_subs["status"] = elwog_subs.status.astype(int)
    elwog_subs["in_service"] = elwog_subs.in_service.map({"ja": True, "nein": False})
    elwog_subs["lon"] = elwog_subs.lon.str.replace(",", ".").astype(float)
    elwog_subs["lat"] = elwog_subs.lat.str.replace(",", ".").astype(float)

    # Filter out substations not in service in 2022
    elwog_subs = elwog_subs[elwog_subs.in_service]

    # Only keep substations with the appropriate statuses
    elwog_subs = elwog_subs[(elwog_subs.status == 1) | (elwog_subs.status == 0)]

    # create geodataframe
    elwog_subs["point"] = elwog_subs.apply(lambda x: Point(x.lon, x.lat), axis=1)  # type: ignore
    elwog_subs = gpd.GeoDataFrame(elwog_subs, geometry="point", crs=CRS)

    # Find closest substation to the elwog substations
    potential_subs = subs[subs["type"] != "missing_line_connection_substation"]

    # Add which operator area the substations are part of
    operator_areas = gpd.read_file("data/operators/OperatorAreas.shp").rename(columns={"NAME": "operator_area"})

    potential_subs = (
        gpd.sjoin(
            potential_subs.to_crs(AUSTRIA_CRS),
            operator_areas[["operator_area", "geometry"]].to_crs(AUSTRIA_CRS),
            how="left",
        )
        .to_crs(CRS)
        .drop(columns="index_right")
    )

    elwog_subs = (
        gpd.sjoin(
            elwog_subs.to_crs(AUSTRIA_CRS),
            operator_areas[["operator_area", "geometry"]].to_crs(AUSTRIA_CRS),
            how="left",
        )
        .to_crs(CRS)
        .drop(columns="index_right")
    )

    # For each elwog sub, find the closest sub in the same operator area
    closest_subs = gpd.GeoDataFrame()
    for operator_area, relevant_elwog_subs in elwog_subs.groupby("operator_area"):
        assert isinstance(relevant_elwog_subs, gpd.GeoDataFrame)

        relevant_subs = potential_subs[potential_subs.operator_area == operator_area]

        closest_subs = pd.concat(
            (
                closest_subs,
                gpd.sjoin_nearest(
                    relevant_elwog_subs.to_crs(AUSTRIA_CRS),
                    relevant_subs.to_crs(AUSTRIA_CRS),
                    how="left",
                    distance_col="distance",
                ),
            )
        )
    assert isinstance(closest_subs, gpd.GeoDataFrame)

    if config.MISSING_CONSUMER_SUBS:
        vprint("Creating csv file containing information on missing elwog substations in OSM data.")
        from extras.identify_missing_consumer_subs import find_missing_subs

        find_missing_subs(closest_subs)

    # Create a mapping from "index_right" (i.e substation index) to a list of all elwog_ids with that substation as
    # closest substation
    sub_to_elwog = (
        closest_subs.groupby("index_right")["elwog_id"]
        .agg(list)
        .reset_index()
        .rename(columns={"index_right": "substation_index"})
    )

    subs["elwog_id"] = sub_to_elwog.set_index("substation_index")

    closest_subs_ids = sub_to_elwog.substation_index

    is_virtual = subs["type"].str.contains("missing")
    closest_virtual_subs = closest_subs_ids[closest_subs_ids.isin(subs[is_virtual].index)]
    closest_real_subs = closest_subs_ids[closest_subs_ids.isin(subs[~is_virtual].index)]

    subs.loc[closest_virtual_subs, "type"] = "virtual_consumer_substation"
    subs.loc[closest_real_subs, "type"] = "consumer_substation"

    # Update names of substations without name to match the first of its elwog substations
    consumer_subs = subs.loc[closest_subs_ids]
    consumer_subs_without_name = consumer_subs[consumer_subs.name.isna()]
    first_elwog_id = consumer_subs_without_name.elwog_id.apply(lambda x: x[0])
    elwog_names = elwog_subs.set_index("elwog_id").loc[first_elwog_id].name
    subs.loc[consumer_subs_without_name.index, "name"] = elwog_names.to_list()

    return subs


# Substations where it makes sense to mark an Austrian substation as an import/export sub.
# A list of country code, OSM id, and voltage level combinations
country_substation_ids: list[tuple[str, int, int]] = [
    ("IT", 1047447425, 220000),  # Nauders
    ("DE", 81540198, 220000),  # St. Peter
]

# The country code, location, and voltage of substations outside of Austria.
country_substation_location: list[tuple[str, Point, int]] = [
    ("DE", Point(9.6447939, 47.7455989), 220000),  # Grünkraut
    ("DE", Point(9.8009972, 47.6535062), 380000),  # Obermooweiler
    ("DE", Point(10.3646495, 47.7378443), 380000),  # Leupolz
    ("DE", Point(10.3646495, 47.7378443), 220000),  # Leupolz
    ("DE", Point(11.2775034, 47.4963392), 220000),  # Krün
    ("DE", Point(13.7095548, 48.5195579), 220000),  # Jochenstein
    ("CZ", Point(16.1165304, 49.1065506), 380000),  # Slavětice
    ("CZ", Point(16.6966118, 49.1083922), 220000),  # Sokolnice
    ("HU", Point(17.6926957, 47.6754244), 380000),  # Győr
    ("HU", Point(17.6926957, 47.6754244), 220000),  # Győr
    ("SI", Point(15.6959009, 46.5236227), 380000),  # Maribor
    ("SI", Point(15.1281716, 46.2783173), 220000),  # Podlog
    ("IT", Point(12.3023364, 46.2016535), 220000),  # Soverzene
    ("CH", Point(10.3335404, 46.8055176), 380000),  # Pradella
    ("CH", Point(9.5547923, 47.3024310), 220000),  # Ruti
]


def get_import_export_substations(subs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Marks the specified substations as import/export substation.
    Uses two methods for marking substations:
    Internal substations that are in austria are marked specifically by osm id in country_substation_ids.
    External substations, where a location is specified and
    """
    subs = subs.copy()
    subs["export_voltage"] = None
    subs["export_country"] = None

    # Mark specific osm substations as import/export subs
    for country, osm_id, voltage in country_substation_ids:
        sub = subs[subs.id == osm_id]
        if len(sub) != 1:
            continue
        sub = sub.iloc[0]
        assert voltage in sub.voltage
        subs.at[sub.name, "type"] = "import_export"
        subs.at[sub.name, "export_voltage"] = [voltage]  # type: ignore
        subs.at[sub.name, "export_country"] = country

    # Find the "missing endstation" substations closest to the external substations
    # Prepare the set of external substations
    external_substations = gpd.GeoDataFrame(
        country_substation_location,
        columns=["country", "point", "voltage"],  # pyright: ignore[reportArgumentType]
        crs=CRS,
        geometry="point",
    )

    for voltage in external_substations.voltage.unique():
        # Find potential substations to mark
        missing_endstations = subs[subs["type"].str.contains("missing") | subs["type"].str.contains("import")]
        rel_missing_endstations = missing_endstations[
            missing_endstations.voltage.apply(lambda v, voltage=voltage: voltage in v)
        ]
        assert isinstance(rel_missing_endstations, gpd.GeoDataFrame)

        rel_external_substations = external_substations[external_substations.voltage == voltage]

        # Find the closest relevant missing endstation to each relevant external substation
        closest_missing_subs = gpd.sjoin_nearest(
            rel_external_substations.to_crs(AUSTRIA_CRS), rel_missing_endstations.to_crs(AUSTRIA_CRS), how="left"
        )
        closest_missing_subs.set_index("index_right", inplace=True)

        subs.loc[closest_missing_subs.index, "type"] = "import_export"
        subs.loc[closest_missing_subs.index, "export_country"] = closest_missing_subs.country
        subs.loc[closest_missing_subs.index, "export_voltage"] = closest_missing_subs.apply(
            _append_external_voltage_level, axis=1
        )  # type: ignore

    return subs


def _append_external_voltage_level(sub):
    """Takes a closest_missing_sub substation (with columns "export_voltage" and "voltage_left"),
    and returns a list of voltages, where "voltage_left" is appended to the existing "export_voltage"
    list (or a list with only the "voltage_left" voltage, if no "export_voltage" list exists.)"""
    if pd.isna(sub.export_voltage):
        return [sub.voltage_left]
    return sub.export_voltage + [sub.voltage_left]
