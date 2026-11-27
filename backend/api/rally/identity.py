"""Keeps a label on each player (P1 to P4) from one sample to the next, by where the player stands on the court.

Each sample gives the people on the court in metres. A detected person takes the label of the nearest known player, if that
player was not further than MAX_JUMP_M away in the last sample. A person with no close known player takes a free label, in
the order of the sides. Labels are kept for a player who is not seen in a sample. Players who switch ends are re-linked by
where they are, so a switch in the middle of a rally can swap two labels: a known limit.
"""

import math
from collections.abc import Mapping, Sequence

MAX_PLAYERS = 4
MAX_JUMP_M = 4.0  # a player does not move further than this between two samples (half a second)
SIDE_ORDER = ("near-left", "near-right", "far-right", "far-left")  # the order in which new players get a label


def assign_labels(
    known: Mapping[int, tuple[float, float]], people: Sequence[dict[str, object]]
) -> tuple[list[dict[str, object]], dict[int, tuple[float, float]]]:
    """The people with their label (1 to 4), and the positions of the known players after this sample."""
    ranked = sorted(people, key=lambda person: -float(person["score"]))[:MAX_PLAYERS]
    pairs = sorted(
        (math.dist((float(person["x_m"]), float(person["y_m"])), position), index, label)
        for index, person in enumerate(ranked)
        for label, position in known.items()
    )
    labels: dict[int, int] = {}
    used_labels: set[int] = set()
    for distance, index, label in pairs:
        if distance > MAX_JUMP_M or index in labels or label in used_labels:
            continue
        labels[index] = label
        used_labels.add(label)
    reserved = used_labels | set(known)  # a player not seen in this sample still keeps the label
    free = [label for label in range(1, MAX_PLAYERS + 1) if label not in reserved]
    newcomers = sorted((index for index in range(len(ranked)) if index not in labels), key=lambda i: SIDE_ORDER.index(str(ranked[i]["side"])))
    for index in newcomers:
        if not free:
            break
        labels[index] = free.pop(0)
    placed = [{**ranked[index], "id": labels[index]} for index in sorted(labels)]
    positions = {**known, **{int(person["id"]): (float(person["x_m"]), float(person["y_m"])) for person in placed}}
    return placed, positions
