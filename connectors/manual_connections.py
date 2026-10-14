import geopandas as gpd
import pandas as pd
from shapely import LineString, Point

from util.utils import AUSTRIA_CRS, CRS

# A list of manual connections to make, containing:
# Starting point
# End point
# Line voltage
# Wires
# Circuits
connection_locations: list[tuple[Point, Point, int, str, int]] = [
    # Virtual substations by Ering-Frauenstein in Germany
    (Point(13.16228, 48.29163), Point(13.16360, 48.29484), 110000, "single", 1),
    # Ering-Frauenstein to Egglfing, a line that goes through Germany
    (Point(13.31861, 48.32061), Point(13.15993, 48.29226), 110000, "single", 1),
    # These connections are needed with 2022 data, but not 2026 data
    # In the 2022 data, a part of a line connecting Umspannwerk Raab to Umspannwerk Ried is missing
    (Point(13.51499, 48.21067), Point(13.54080, 48.24324), 110000, "single", 1),
    # In the 2022 data, a part of a line connecting Umspannwerk Stadlau to Umspannwerk Essling is missing
    (Point(16.49294, 48.21705), Point(16.45874, 48.22692), 110000, "single", 2),
    # In the 2022 data, a part of a line connecting Umspannwerk Heiligenstadt to Umspannwerk Wien Nord is missing
    (Point(16.36245, 48.24411), Point(16.38992, 48.25756), 110000, "single", 2),
    # Line connecting 110kV Hagenau (33003245) and 220kV Salzach Stich (33041399) missing
    (Point(13.02965, 47.83106), Point(13.02775, 47.83325), 220000, "double", 2),
]

# If voltage level of a substation has to be extended for the connections, that can be added here
sub_vol_change: list[tuple[int, tuple[int, ...]]] = [
    # Hagenau should be connected with Salzach Stich 220kV (33041399)
    (33003245, (110000, 220000))
]


def add_manual_connections(lines: pd.DataFrame, subs: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Create new lines from the connection_locations list.
    Finds the substations closest to the start and end points, and set these as connected substations.
    """
    subs = subs.copy()
    for sub_id, voltage in sub_vol_change:
        subs.at[subs[subs.id == sub_id].index[0], "voltage"] = list(voltage)  # type: ignore

    manual_connections = gpd.GeoDataFrame(
        connection_locations,
        columns=["start", "end", "voltage", "wires", "circuits"],  # pyright: ignore[reportArgumentType]
        crs=CRS,
        geometry="start",
    )

    all_new_lines = []
    num_new_lines = 0
    for voltage in manual_connections.voltage.unique():
        # Only connect to substation with the correct voltage level
        connections = manual_connections[manual_connections.voltage == voltage].copy()
        rel_subs = subs[subs.voltage.apply(lambda v, voltage=voltage: voltage in v)]

        # Find closest substations to the start and end of the new lines
        start_subs = gpd.sjoin_nearest(connections.to_crs(AUSTRIA_CRS), rel_subs.to_crs(AUSTRIA_CRS), how="left")
        end_subs = gpd.sjoin_nearest(
            connections.set_geometry("end").set_crs(CRS).to_crs(AUSTRIA_CRS), rel_subs.to_crs(AUSTRIA_CRS), how="left"
        )

        # Make sure manual connection does not connect the same substation at both ends
        assert (start_subs.id != end_subs.id).all()

        # Calculate and assign parameters to the new lines
        connections["start_sub_loc"] = start_subs.apply(lambda s: Point(s.lon, s.lat), axis=1)
        connections["end_sub_loc"] = end_subs.apply(lambda s: Point(s.lon, s.lat), axis=1)
        line_geometries = connections.apply(
            lambda x: LineString([x.start_sub_loc, x.start, x.end, x.end_sub_loc]), axis=1
        )

        new_lines = gpd.GeoDataFrame(columns=lines.columns, crs=CRS, geometry="geometry")

        new_lines["voltage"] = connections.voltage
        new_lines["geometry"] = line_geometries
        new_lines["substation_1"] = start_subs.id
        new_lines["substation_2"] = end_subs.id
        new_lines["wires"] = connections.wires
        new_lines["circuits"] = connections.circuits
        new_lines["id"] = new_lines.apply(
            lambda x, num_new_lines=num_new_lines: f"manual line {x.name + num_new_lines}", axis=1
        )
        new_lines["length"] = new_lines.to_crs(AUSTRIA_CRS).length

        new_lines.replace(pd.NA, None, inplace=True)

        all_new_lines.append(new_lines)
        num_new_lines = len(new_lines)

    # Add the new lines to the original lines
    lines = pd.concat([lines, *all_new_lines]).reset_index(drop=True)
    lines = gpd.GeoDataFrame(lines, crs=CRS, geometry="geometry")

    return lines, subs
