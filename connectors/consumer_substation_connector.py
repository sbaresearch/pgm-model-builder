import geopandas as gpd
import pandas as pd


def connect_consumer_to_substation(consumers: gpd.GeoDataFrame, substations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Connects consumers to substations based on the elwog ids specified in community_substation_connections.csv."""
    cons = consumers.copy()
    subs = substations.copy()

    # Load consumer substation connections
    community_substation_df = pd.read_csv("data/consumers/community_substation_connections.csv", sep=";")
    community_substation_df.drop(columns=["g_name", "USPW-Name"], inplace=True)
    community_substation_df.rename(columns={"GdeCode": "gkz", "USPW-ID": "elwog_id"}, inplace=True)

    # Add which elwog sub the consumer is connected to
    cons_with_elwog_id = pd.merge(cons, community_substation_df, on="gkz")

    # Find the substation id for each consumer from the elwog id
    def find_sub_id_from_elwog_id(elwog_id: list | None):
        def id_in_list(elwog_id_list):
            return elwog_id in elwog_id_list if isinstance(elwog_id_list, list) else False

        return subs[subs.elwog_id.apply(id_in_list)].iloc[0].id

    cons["substation_id"] = cons_with_elwog_id.elwog_id.apply(find_sub_id_from_elwog_id)

    return cons
