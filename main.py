from datetime import datetime

from model_builder import build_model
from util import config
from util.utils import get_model_path


def profile_main():
    import cProfile
    import io
    import pstats

    pr = cProfile.Profile()
    pr.enable()

    build_model()

    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).strip_dirs().sort_stats("cumtime")
    ps.print_stats(30)  # Only print top 30 lines
    print(s.getvalue())


def create_results_dir(name: str | None):
    import os

    if not os.path.isdir("results/visualisation"):
        os.makedirs("results/visualisation")
    if not os.path.isdir("results/extras"):
        os.makedirs("results/extras")

    filename = "results/"
    if name is None:
        filename += datetime.now().strftime("%Y_%m_%d_%H_%M_%S")  # noqa: DTZ005
    else:
        filename += name
    config.EXPORT_DIR = filename

    if os.path.exists(filename):
        raise NameError("Stated path for result directory already exists")

    os.makedirs(filename)

    if config.GEOJSON:  # only create dir if any maps/graphs will be created
        os.makedirs(filename + "/visualisation")
    if config.MISSING_CONSUMER_SUBS:
        os.makedirs(filename + "/extras")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load power system data and create a power grid model.")
    parser.add_argument(
        "-ms",
        "--missing_consumer_subs",
        action="store_true",
        help="Creates a csv file with information about ELWOG-Plus substations that could not be found"
        " in the substation data.",
    )
    parser.add_argument("-gj", "--geojson", action="store_true", help="Creates a GeoJson file with the location data.")
    parser.add_argument(
        "-uc",
        "--use_cache",
        action="store_true",
        help="For debug purposes: Use a cached version of the lines and substations, to not have to run"
        " the lines substation connections every time. Caches the results of the calculations if false.",
    )
    parser.add_argument("-p", "--profile", action="store_true", help="Enable profiling with cProfile")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Prints extra information about the process. Only prints warnings if false.",
    )
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        help="Name of the directory where the results are placed. "
        "The directory is put in the results folder. Default: time of execution."
        "Note: Also always places the newest results directly in the results dir.",
        default=None,
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        help="Path to model file to use. Default: Most recent model in the data/model dir (based on model name).",
    )

    args = parser.parse_args()
    config.VERBOSE = args.verbose
    config.GEOJSON = args.geojson
    config.USE_CACHE = args.use_cache
    config.MISSING_CONSUMER_SUBS = args.missing_consumer_subs

    config.MODEL_PATH = get_model_path(args.model)

    create_results_dir(args.name)

    if args.profile:
        print("Profiling enabled...")
        profile_main()
    else:
        build_model()
