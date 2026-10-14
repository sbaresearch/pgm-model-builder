from random import random

import geopandas as gpd
from shapely import LineString
from shapely.affinity import translate

from util import config
from util.utils import AUSTRIA_CRS, CRS, vprint


class GeoJsonExporter:
    lines: gpd.GeoDataFrame
    subs: gpd.GeoDataFrame
    gens: gpd.GeoDataFrame

    gen_sub_connections: gpd.GeoDataFrame

    def __init__(self, lines: gpd.GeoDataFrame, subs: gpd.GeoDataFrame, gens: gpd.GeoDataFrame):
        self.lines = lines.copy()
        self.subs = subs.copy()
        self.gens = gens.copy()

    def prepare_for_export(self):
        # Prepare lines
        self.lines["type"] = "sub to sub"
        self._add_line_color()
        self._add_line_width()
        self._shift_lines()
        self._reorder_line_columns()

        # Prepare substations
        self._add_sub_color()
        self._reorder_sub_columns()

        # Prepare generators
        self._add_gen_color()
        self._change_gen_unit()
        self.gen_sub_connections = self._create_gen_sub_connections()
        self._reorder_gen_columns()

    def export(self):
        if not hasattr(self, "gen_sub_connections"):
            vprint("Could not find generator to substation connection dataframe. Creating these...")
            self.prepare_for_export()

        destination_dirs = [f"{config.EXPORT_DIR}/visualisation", "results/visualisation"]
        for dir in destination_dirs:
            self.lines.to_file(f"{dir}/lines.geojson", driver="GeoJSON")
            self.subs.to_file(f"{dir}/substations.geojson", driver="GeoJSON")
            self.gens.to_file(f"{dir}/generators.geojson", driver="GeoJSON")
            self.gen_sub_connections.to_file(f"{dir}/gen_to_sub.geojson", driver="GeoJSON")

    def _add_line_color(self):
        self.lines["stroke"] = "#00FF00"
        colors = {
            110000: "#00FF00",
            220000: "#FF0000",
            380000: "#0000FF",
        }

        self.lines["stroke"] = self.lines.voltage.apply(lambda v: colors[v])

    def _add_line_width(self):
        self.lines["stroke-width"] = 2
        stroke_widths = {
            110000: 2,
            220000: 4,
            380000: 6,
        }

        self.lines["stroke-width"] = self.lines.voltage.apply(lambda v: stroke_widths[v])

    def _shift_lines(self):
        max_shift = 0.00003
        self.lines["geometry"] = self.lines.geometry.apply(
            lambda x: translate(x, xoff=random() * max_shift, yoff=random() * max_shift)
        )

    def _reorder_line_columns(self):
        ordered = ["type", "voltage", "ref", "wires", "id", "length"]
        self.lines = self.lines[  # type: ignore
            ordered + [col for col in self.lines.columns if col not in ordered]
        ]

    def _add_sub_color(self):
        self.subs["fill"] = "#00FF00"
        self.subs.loc[self.subs["type"].str.contains("virtual"), ["fill"]] = "#999999"
        self.subs.loc[self.subs["type"].str.contains("import_export"), ["fill"]] = "#0099FF"

    def _reorder_sub_columns(self):
        ordered = ["type", "voltage", "name", "id"]
        self.subs = self.subs[ordered + [col for col in self.subs.columns if col not in ordered]]  # type: ignore

    def _add_gen_color(self):
        self.gens.loc[self.gens["type"] == "way", ["fill"]] = "#FF0000"
        self.gens.loc[self.gens["type"] == "relation", ["fill"]] = "#FF9900"

    def _change_gen_unit(self):
        self.gens["output_MW"] = self.gens.output_w / 1e6
        self.gens.drop(columns="output_w", inplace=True)

    def _create_gen_sub_connections(self) -> gpd.GeoDataFrame:
        subs = self.subs.to_crs(AUSTRIA_CRS)
        gens = self.gens.to_crs(AUSTRIA_CRS)

        subs["centroid"] = subs.geometry.apply(lambda x: x.centroid)

        sub_lookup = subs.set_index("id").centroid

        gens["start"] = gens.geometry.apply(lambda x: x.centroid)
        gens["end"] = gens.substation_id.map(sub_lookup)
        gens["line"] = gens.apply(lambda x: LineString([x.start, x.end]), axis=1)

        gen_sub_connections = gens[["name", "id", "substation_id", "line"]].copy()
        gen_sub_connections["type"] = "gen to sub"
        gen_sub_connections.set_geometry("line", inplace=True)
        gen_sub_connections.set_crs(AUSTRIA_CRS, inplace=True)
        gen_sub_connections.to_crs(CRS, inplace=True)
        gen_sub_connections.rename(columns={"name": "generator_name", "id": "generator_id"}, inplace=True)  # pyright: ignore[reportCallIssue]
        gen_sub_connections["fill"] = "#FF9900"
        gen_sub_connections["stroke-width"] = 1

        # reorder columns
        gen_sub_connections = gen_sub_connections[
            ["type", "generator_name", "generator_id", "substation_id", "line", "fill", "stroke-width"]
        ]

        return gen_sub_connections  # pyright: ignore[reportReturnType]

    def _reorder_gen_columns(self):
        ordered = ["type", "name", "output_MW", "source", "substation_id"]
        self.gens = self.gens[ordered + [col for col in self.gens.columns if col not in ordered]]  # pyright: ignore[reportAttributeAccessIssue]
