import os
import webbrowser
from collections import defaultdict
from itertools import combinations, permutations
from typing import Literal, overload

import geopandas as gpd
import pandas as pd
from shapely import LineString, Point
from tqdm import tqdm

from util.utils import AUSTRIA_CRS, CRS, LineRefMatchError, tabbed_tqdm_format, vprint

lost_circuits: dict[LineRefMatchError, int] = defaultdict(int)


def remove_virtual_substations(
    lines: gpd.GeoDataFrame, subs: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Goes through all virtual substations and tries to connect all lines connected to the substation.
    If able, removed the substation from the set of substations.
    If unable, keeps the substation as to not lose any lines. Marks the remaining virtual substations
    based on the reason for keeping them.
    """
    lines = lines.copy()
    subs = subs.copy()

    virtual_subs = subs[subs["type"] == "virtual_substation"]

    vsubs_to_remove = []
    vsubs_leftover = defaultdict(int)
    with tqdm(total=len(virtual_subs), bar_format=tabbed_tqdm_format) as pbar:
        for idx, vsub in virtual_subs.iterrows():
            pbar.update(1)

            connected_lines = lines[(lines.substation_1 == vsub.id) | (lines.substation_2 == vsub.id)].copy()

            connected_lines["other_sub"] = connected_lines.apply(
                lambda l, vsub_id=vsub.id: l["substation_1"] if l["substation_1"] != vsub_id else l["substation_2"],
                axis=1,
            )

            if len(connected_lines.other_sub.unique()) == 1:
                # only connecting to one other substation
                vsub_type = "missing_endstation"
                subs.at[idx, "type"] = vsub_type  # type: ignore
                vsubs_leftover[vsub_type] += 1
                continue

            pairs = _find_pairs(connected_lines, str(vsub.id), vsub.geometry.centroid)  # pyright: ignore[reportArgumentType]
            if pairs is None:
                vsub_type = "missing_line_connection_substation"
                subs.at[idx, "type"] = vsub_type  # type: ignore
                vsubs_leftover[vsub_type] += 1
                continue

            lines.drop(connected_lines.index, inplace=True)  # type: ignore

            if pairs:
                assert all(len(df) == 2 for df in pairs)

                new_lines = _connect_lines(pairs)

                lines = gpd.GeoDataFrame(pd.concat([lines, new_lines]), geometry="geometry", crs=CRS).reset_index(  # pyright: ignore[reportAssignmentType]
                    drop=True
                )

            vsubs_to_remove.append(idx)

    # Cleanup line columns
    columns_to_drop = ["other_sub", "_ref_split"]
    lines.drop(columns=[c for c in columns_to_drop if c in lines.columns], inplace=True)

    # Update Length
    lines["length"] = lines.to_crs(AUSTRIA_CRS).length

    vprint(
        f"Could remove {len(vsubs_to_remove)} virtual subs, leaving {len(virtual_subs) - len(vsubs_to_remove)}, of which:"
    )
    for vsub_type, amount in vsubs_leftover.items():
        vprint(f"\t {amount:<4} are {vsub_type}")
    vprint(f"Lost {sum(lost_circuits.values())} circuits when removing virtual substations:")
    for error, amount in lost_circuits.items():
        vprint(f"\t{error.name:<22}: {amount}")

    subs.drop(index=vsubs_to_remove, inplace=True)

    return lines, subs


os.environ.pop("GTK_MODULES", None)


def open_location(location: Point):
    url = 'https://overpass-turbo.eu/?Q=[out:json][timeout:25];way["power"="line"]["voltage"]({{bbox}});out geom;&C='
    url += f"{location.y};{location.x};17"
    webbrowser.open(url, new=2)


def debug_line(connected_lines, lines, location):
    open_location(location)
    vprint(str(connected_lines.drop(columns=["geometry", "operator"])))
    vprint(str(lines.drop(columns=["geometry", "operator"])))
    vprint("")


def _find_pairs(connected_lines: pd.DataFrame, vsub_id: str, vsub_location: Point) -> list[pd.DataFrame] | None:
    """
    Find pairs of lines with the same reference. First pairs them all using the full reference, then goes through any remaining ones and try
    to pair them using only the first part of the reference.
    """
    lines = connected_lines.copy()

    # Ignore ref in case there is a unique solution to connecting the substations
    pairs = _find_unique_solution(lines)
    if pairs is not None:
        return pairs

    if lines.ref.isna().all():
        vprint(
            f"\tLine ref match error {LineRefMatchError.ALL_NA_CIRCUIT_MISMATCH.name}: "
            f"(vsub_id={vsub_id}, lost circuits = {lines.circuits.sum()}) "
            f"All lines have na ref, and could not find a way to match circuits."
        )
        # debug_line(connected_lines, na_lines, vsub_location)
        lost_circuits[LineRefMatchError.ALL_NA_CIRCUIT_MISMATCH] += lines.circuits.sum()
        return None

    lines = _explode_lines(lines)

    if len(lines) % 2 != 0:
        vprint(
            f"\tLine ref match error {LineRefMatchError.ODD_CIRCUIT_AMOUNT.name}: "
            f"(vsub_id={vsub_id}, lost circuits = {lines.circuits.sum()}) "
            f"{len(lines)} connected circuits -> cannot connect all."
        )
        # debug_line(connected_lines, na_lines, vsub_location)
        lost_circuits[LineRefMatchError.ODD_CIRCUIT_AMOUNT] += lines.circuits.sum()
        return None

    na_ref_mask = lines.ref.isna()
    na_lines = lines[na_ref_mask].copy()
    lines = lines[~na_ref_mask].copy()

    # Try to find pairs based on exact ref
    pairs, triples, leftovers = _find_matches(lines, ["ref", "voltage"], return_triples=True)  # type: ignore

    if len(triples) == 2:
        new_pairs = _handle_two_triples_wiring(triples, vsub_id)
        if new_pairs is not None:
            pairs.extend(new_pairs)
        else:
            leftovers = pd.concat([*triples, leftovers])

    if leftovers.empty and na_lines.empty:
        return pairs

    # Try to match remaining lines based on split ref
    leftovers["_ref_split"] = leftovers["ref"].str.split("/").str[0]
    split_ref_pairs, leftovers = _find_matches(leftovers, ["_ref_split", "voltage"])
    pairs.extend(split_ref_pairs)

    if leftovers.empty and na_lines.empty:
        return pairs
    elif leftovers.empty:
        # leftovers empty but na_lines not
        leftovers = na_lines
    else:
        # neither empty
        leftovers = pd.concat([na_lines, leftovers])

    # Try to match remaining lines without caring about the ref
    no_ref_pairs, leftovers = _find_matches(leftovers, ["voltage"])  # pyright: ignore[reportArgumentType]
    pairs.extend(no_ref_pairs)

    # Print error message if there are circuits leftover
    if not leftovers.empty:
        if len(leftovers) == 1:
            vprint(
                f"\tLine ref match error {LineRefMatchError.ONE_LEFTOVER_LINE.name}: "
                f"(vsub_id={vsub_id}, lost circuits = 1) "
                f"Could not find a matching ref for ref={leftovers.ref.iloc[0]}."
            )
            # debug_line(connected_lines, lines, vsub_location)
            lost_circuits[LineRefMatchError.ONE_LEFTOVER_LINE] += 1
        else:
            vprint(
                f"\tLine ref match error {LineRefMatchError.NO_MATCHES.name}: "
                f"(vsub_id={vsub_id}, lost circuits = {len(leftovers)})"
            )
            # debug_line(connected_lines, lines, vsub_location)
            lost_circuits[LineRefMatchError.NO_MATCHES] += len(leftovers)
        return None

    return pairs


def _find_unique_solution(lines: pd.DataFrame) -> None | list[pd.DataFrame]:
    """Checks if the lines connect every "other_sub" to each other. i.e:
    Every "other_sub" should have exactly (num_subs-1)*n lines connected (for any n).
    Has to be true for every voltage level."""
    lines_per_voltage = {}
    for vol, group in lines.groupby("voltage"):
        exploded_lines = _expand_physical_circuits(group)
        lines_per_voltage[vol] = exploded_lines

        lines_per_sub = [sum(exploded_lines.other_sub == sub) for sub in exploded_lines.other_sub.unique()]
        if len(set(lines_per_sub)) > 1:
            return None  # all subs do not have the same number of connected lines

        # We now know all subs have the same number of connected lines
        lines_per_sub = lines_per_sub[0]

        num_subs = len(exploded_lines.other_sub.unique())
        if num_subs < 2:
            return None
        should_have = num_subs - 1  # How many lines should be connected to each sub (up to a factor n)

        if lines_per_sub % should_have != 0:
            return None

    pairs = []
    for _lines in lines_per_voltage.values():
        pairs.extend(_pair_without_ref(_lines))

    return pairs


def _expand_physical_circuits(lines_to_expand: pd.DataFrame) -> pd.DataFrame:
    """Explodes the given lines into one row per circuit, amending the ids to keep them unique.
    Attempts to create an even number of circuits when any of the lines have na circuits."""
    lines = lines_to_expand.copy()

    na_circuits_mask = lines.circuits.isna()

    if na_circuits_mask.any():
        # Normal case -> guess values for nan circuits. Try to get an even number of circuits overall
        total_circuits = lines.circuits.sum(skipna=True)
        total_na = na_circuits_mask.sum()

        # If there is not an even number of circuits, give the first na lines an extra circuit
        if (total_na + total_circuits) % 2 != 0:
            lines.loc[lines.index[na_circuits_mask][0], "circuits"] = 2

        # Give all (remaining) na lines a value of one
        lines["circuits"] = lines.circuits.where(~lines.circuits.isna(), 1)

    # explode into one row per circuit
    expanded = lines.loc[lines.index.repeat(lines["circuits"])]

    # Add extra id digit for each exploded row
    expanded["_circuit_idx"] = expanded.groupby(level=0).cumcount() + 1
    expanded["id"] = expanded.apply(
        lambda line: f"{line.id}/{line._circuit_idx}" if len(expanded[expanded.id == line.id]) > 1 else line.id, axis=1
    )
    expanded.drop(columns="_circuit_idx", inplace=True)

    # each expanded row is now exactly one circuit
    expanded["circuits"] = 1

    return expanded.reset_index(drop=True)


def _pair_without_ref(lines: pd.DataFrame) -> list[pd.DataFrame]:
    """Returns a list of dfs, each with two lines taken from the given group.
    Makes sure the pairs have different other_sub values."""
    pairs = []

    # Bucket physical circuits by other sub
    line_by_sub = defaultdict(list)
    for _, line in lines.iterrows():
        line_by_sub[line.other_sub].append(line)

    # track how often sub-pairs are used (using a tuple of subs as key)
    pair_counts = defaultdict(int)

    while True:
        # subs that still have a line connected
        subs = [s for s, lines in line_by_sub.items() if lines]
        if len(subs) < 2:
            break

        sub_pair_candidates = []

        for sub1, sub2 in combinations(subs, 2):
            if line_by_sub[sub1] and line_by_sub[sub2]:
                sub_pair = tuple(sorted((sub1, sub2)))
                sub_pair_candidates.append((pair_counts[sub_pair], sub_pair, sub1, sub2))

        if not sub_pair_candidates:
            break

        # choose the least-used sub-pair
        _, sub_pair, sub1, sub2 = min(sub_pair_candidates)

        line1 = line_by_sub[sub1].pop()
        line2 = line_by_sub[sub2].pop()

        pair_counts[sub_pair] += 1
        pairs.append(pd.DataFrame([line1, line2]))

    return pairs


def _explode_lines(lines: pd.DataFrame) -> pd.DataFrame:
    expanded_lines = []
    for group in _get_possible_connection_groups(lines, ["ref", "voltage"]):
        expanded_lines.append(_expand_physical_circuits(group))

    return pd.concat(expanded_lines)


def _get_possible_connection_groups(lines: pd.DataFrame, group_by: list[str]):
    """A generator that yields dfs of lines (from the given lines) that have the same group_by parameters,
    and different other_sub."""
    for _, group in lines.groupby(group_by, dropna=False):
        different_sub_groups = _ungroup_same_sub_lines(group)
        yield from different_sub_groups


def _ungroup_same_sub_lines(lines: pd.DataFrame) -> list[pd.DataFrame]:
    """Returns a list of dfs containing the rows from lines, but with each df only containing rows with different other_sub."""
    lines = lines.copy().reset_index(drop=True)

    different_sub_groups = []
    while not lines.empty:
        mask = ~lines.other_sub.duplicated()
        different_sub_groups.append(lines[mask])
        lines.drop(lines[mask].index, inplace=True)  # type: ignore

    return different_sub_groups


@overload
def _find_matches(
    lines: pd.DataFrame, group_by: list[str], return_triples: Literal[True]
) -> tuple[list[pd.DataFrame], list[pd.DataFrame], pd.DataFrame]: ...


@overload
def _find_matches(
    lines: pd.DataFrame, group_by: list[str], return_triples: Literal[False] = False
) -> tuple[list[pd.DataFrame], pd.DataFrame]: ...


def _find_matches(
    lines: pd.DataFrame, group_by: list[str], return_triples: bool = False
) -> tuple[list[pd.DataFrame], pd.DataFrame] | tuple[list[pd.DataFrame], list[pd.DataFrame], pd.DataFrame]:
    pairs = []
    triples = []
    leftovers = []
    for group in _get_possible_connection_groups(lines, group_by):
        if len(group) == 2:
            pairs.append(group)
        elif return_triples and len(group) == 3:
            triples.append(group)
        else:
            leftovers.append(group)
    leftovers = pd.concat(leftovers) if len(leftovers) else pd.DataFrame(columns=lines.columns)

    if return_triples:
        return pairs, triples, leftovers

    return pairs, leftovers


def _handle_two_triples_wiring(triples: list[pd.DataFrame], vsub_id: str) -> list[pd.DataFrame] | None:
    """One special case is where there is a T-connection, but only one or two reference numbers are used.
    This matches them up in a way where no pairs share both substations.

    A       A                        A       A
    ====X====            ->          ====X====
    B   ||  B                        B   ||  C
       A||B                             B||C
        ||                               ||
        X                                X

    """
    assert len(triples) == 2
    assert all(len(df) == 3 for df in triples)

    df1, df2 = triples[0].copy().reset_index(drop=True), triples[1].copy().reset_index(drop=True)

    perms = permutations(df2.index)

    try:
        perm = next(
            p for p in perms if all(df1.loc[i, "other_sub"] != df2.loc[j, "other_sub"] for i, j in enumerate(p))
        )
    except:  # noqa: E722
        vprint(f"\tTrying to match ’two triples’ wiring for vsub {vsub_id}, but cannot find a solution.")
        return None

    dfs = [pd.concat([df1.iloc[[i]], df2.loc[[j]]], ignore_index=True) for i, j in enumerate(perm)]

    return dfs


def _connect_lines(ref_pairs: list[pd.DataFrame]) -> pd.DataFrame:
    connected_lines = []
    for df in ref_pairs:
        connected_lines.append(_merge_pair(df))
    return pd.concat(connected_lines)


def _merge_pair(df: pd.DataFrame) -> pd.DataFrame:
    l1, l2 = df.iloc[0], df.iloc[1]
    l1_coords, l2_coords = l1.geometry.coords, l2.geometry.coords

    merged_line = l1.combine_first(l2)

    # Do not copy ref
    if l1.ref != l2.ref:
        merged_line.ref = None  # type: ignore

    # Merge geometry based on which substations match
    if l1.substation_2 == l2.substation_1:
        coords = l1_coords[:] + l2_coords[1:]
        s1, s2 = l1.substation_1, l2.substation_2
    elif l1.substation_1 == l2.substation_2:
        coords = l2_coords[:] + l1_coords[1:]
        s1, s2 = l2.substation_1, l1.substation_2
    elif l1.substation_1 == l2.substation_1:
        coords = l1_coords[::-1] + l2_coords[1:]
        s1, s2 = l1.substation_2, l2.substation_2
    elif l1.substation_2 == l2.substation_2:
        coords = l1_coords[:] + l2_coords[:-1][::-1]
        s1, s2 = l1.substation_1, l2.substation_1
    else:
        raise ValueError("No matching substations!")

    merged_line["geometry"] = LineString(coords)
    merged_line["substation_1"], merged_line["substation_2"] = s1, s2

    # Create merged id.
    merged_line["id"] = f"({l1.id})-({l2.id})"

    merged_line = pd.DataFrame([merged_line])

    return merged_line
