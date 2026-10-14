from connectors.generator_substation_connector import connect_generator_to_substation
from connectors.line_substation_connector import remove_virtual_substations
from connectors.manual_connections import add_manual_connections
from exporters.geojson_export import GeoJsonExporter
from exporters.model_export import export_model
from loaders.generator_loader import load_generators
from loaders.line_loader import load_lines
from loaders.substation_loader import get_import_export_substations, load_substations, merge_consumer_substations
from util import config
from util.utils import dump_to_cache, load_from_cache, vprint


def build_model():
    vprint("Loading power generators")
    generators = load_generators()

    if config.USE_CACHE:
        vprint("Loading lines and substations from cache")
        lines, substations = load_from_cache()
    else:
        vprint("Loading substations")
        substations = load_substations()

        vprint("Loading lines")
        lines = load_lines()

        vprint("Adding manual lines")
        lines, substations = add_manual_connections(lines, substations)

        vprint("Removing virtual substations")
        lines, substations = remove_virtual_substations(lines, substations)

        vprint("Marking consumer substations")
        substations = merge_consumer_substations(substations)

        dump_to_cache(lines, substations)

    vprint("Connecting power generators to closest substation")
    generators = connect_generator_to_substation(generators, substations)

    vprint("Finding import/export substations")
    substations = get_import_export_substations(substations)

    if config.GEOJSON:
        vprint("Export geojson with location data")
        geojson_exporter = GeoJsonExporter(lines, substations, generators)
        geojson_exporter.prepare_for_export()
        geojson_exporter.export()

    vprint("Exporting model")
    export_model(lines, substations, generators)
