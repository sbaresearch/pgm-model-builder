import geopandas as gpd

from util import config


def find_missing_subs(closest_subs: gpd.GeoDataFrame, tolerance: float = 1000):
    far_away_subs = closest_subs[closest_subs["distance"] > tolerance].copy()

    far_away_subs["name_right"] = far_away_subs.name_right.fillna("")

    far_away_subs["extracted_name_left"] = far_away_subs.name_left.apply(_extract_name)
    far_away_subs["extracted_name_right"] = far_away_subs.name_right.apply(_extract_name)

    missing_subs = far_away_subs[far_away_subs.extracted_name_left != far_away_subs.extracted_name_right].copy()
    missing_subs["distance"] = missing_subs["distance"].astype(int)

    columns_to_keep = [
        "elwog_id",
        "name_left",
        "betreiber",
        "quelle",
        "status",
        "in_service",
        "lat_left",
        "lon_left",
        "name_right",
        "id",
        "distance",
    ]

    missing_subs = missing_subs[columns_to_keep]
    missing_subs.rename(  # type: ignore
        columns={
            "elwog_id": "USPW-ID",
            "status": "Typ",
            "in_service": "Betrieb 2022",
            "name_left": "Name",
            "lat_left": "Latitude",
            "lon_left": "Longitude",
            "name_right": "Closest OSM substation",
            "id": "Closest OSM substation id",
            "distance": "Distance to OSM substation (m)",
        },
        inplace=True,
    )
    missing_subs = missing_subs.rename(columns=lambda s: s.replace("_", " "))  # type: ignore
    missing_subs = missing_subs.rename(columns=str.capitalize)

    destination_dirs = [f"{config.EXPORT_DIR}/extras", "results/extras"]
    for dir in destination_dirs:
        missing_subs.to_csv(f"{dir}/missing_subs.csv", sep=";", index=False)


def _extract_name(orig_name: str) -> str:
    name = orig_name.lower()
    name = name.strip("*")
    name = name.strip("'")
    name.replace("uw", "umspannwerk")

    # Divide the name into words
    word_list = []
    for sub in name.split(" "):
        for subsub in sub.split("/"):
            for subsubsub in subsub.split("-"):
                word_list.append(subsubsub)  # noqa: PERF402

    words_to_ignore = ["umspannwerk", "unterwerk"]
    word_list = [word for word in word_list if not word in words_to_ignore]
    # Return word with most characters
    return max(word_list, key=len)
