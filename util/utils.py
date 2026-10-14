import pickle
from enum import Enum, auto

import geopandas as gpd
from tqdm import tqdm

from util import config


def vprint(msg: str):
    if config.VERBOSE:
        tqdm.write(msg)


# Used with tqdm to get a tabbed progress bar
tabbed_tqdm_format = "        {l_bar}{bar}{r_bar}"


class LineRefMatchError(Enum):
    ALL_NA_CIRCUIT_MISMATCH = auto()
    ONE_LEFTOVER_LINE = auto()
    NO_MATCHES = auto()
    ODD_CIRCUIT_AMOUNT = auto()


CRS = "EPSG:4326"  # lat lon (what OSM uses)
AUSTRIA_CRS = "EPSG:31287"  # Austria only


def get_model_path(model_path: str | None = None) -> str:
    """Finds latest model path if none is given, otherwise returns the path given."""
    if model_path is not None:
        return model_path
    from os import listdir

    dir_path = "data/model/" + next(iter(sorted(listdir("data/model"), reverse=True)))
    return dir_path


def load_from_cache() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    with open("data/cached_data/lines.pkl", "rb") as f:
        lines = pickle.load(f)
    with open("data/cached_data/substations.pkl", "rb") as f:
        substations = pickle.load(f)

    return lines, substations


def dump_to_cache(lines: gpd.GeoDataFrame, substations: gpd.GeoDataFrame):
    with open("data/cached_data/lines.pkl", "wb") as f:
        pickle.dump(lines, f)
    with open("data/cached_data/substations.pkl", "wb") as f:
        pickle.dump(substations, f)
