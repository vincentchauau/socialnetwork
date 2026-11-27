"""Finds the shuttlecock without training: bright moving spots, linked into tracks that move smoothly.

A candidate is a bright spot that changed since the frame before (static lights, lines and the crowd do not change).
Candidates are linked from frame to frame: each track predicts where it goes next (constant velocity), and a candidate
close to that prediction extends it. The shuttle is the longest recent track. All positions are 0..1 of the frame.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

MOTION_THRESHOLD = 25  # grey-level change between two frames that counts as motion
LOCAL_CONTRAST = 50  # the shuttle is this much brighter than the pixels around it
MIN_BRIGHTNESS = 190  # grey level of the shuttle's centre: nearly white
CLUSTER_RADIUS = 0.04  # share of the frame
CLUSTER_LIMIT = 3  # this many neighbours close by make a cluster
TOPHAT_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
MIN_AREA = 2  # pixels, at the frame's own resolution
MAX_AREA = 30  # the shuttle is a few pixels; a player's white shirt or shoe is bigger
GATE = 0.1  # a candidate this far (share of the frame) from a track's prediction can extend it
MAX_MISS_FRAMES = 4  # a track that is not extended for this many frames stops being the shuttle
EDGE_MARGIN = 0.02  # candidates this close to the frame edge are lights or logos, not the shuttle
BOX_MARGIN = 0.02  # a player's box is grown by this share before candidates are dropped
MIN_TRACK_POINTS = 4  # a track needs this many points before it can be the shuttle
FORGET_FRAMES = 16  # a track not extended for this long is dropped
STRAIGHT_POINTS = 6  # the last points that must lie on a straight line
MIN_STRAIGHTNESS = 0.7  # the straight distance over the walked distance: a shuttle flies straight, a limb swings back


@dataclass(frozen=True)
class Track:
    points: tuple[tuple[int, float, float], ...]  # (frame index, x, y)

    def last(self) -> tuple[int, float, float]:
        return self.points[-1]

    def predicted(self, frame_index: int) -> tuple[float, float]:
        """Where the track should be at this frame, moving at its last velocity."""
        frame, x, y = self.last()
        if len(self.points) < 2:
            return x, y
        prev_frame, prev_x, prev_y = self.points[-2]
        steps = frame - prev_frame
        vx = (x - prev_x) / steps
        vy = (y - prev_y) / steps
        ahead = frame_index - frame
        return x + vx * ahead, y + vy * ahead


def outside_people(
    candidates: list[tuple[float, float]], boxes: list[tuple[float, float, float, float]]
) -> list[tuple[float, float]]:
    """The candidates that are not on a player (inside a box, grown a little) and not at the very edge of the frame."""
    kept = []
    for x, y in candidates:
        if x < EDGE_MARGIN or x > 1 - EDGE_MARGIN or y < EDGE_MARGIN or y > 1 - EDGE_MARGIN:
            continue
        if any(x1 - BOX_MARGIN <= x <= x2 + BOX_MARGIN and y1 - BOX_MARGIN <= y <= y2 + BOX_MARGIN for x1, y1, x2, y2 in boxes):
            continue
        kept.append((x, y))
    return kept


def find_candidates(previous: NDArray[np.uint8], current: NDArray[np.uint8]) -> list[tuple[float, float]]:
    """Spots that are brighter than their own surroundings and moved since the previous frame, as 0..1 of the frame.

    The local brightness (top-hat) finds a small white spot on a bright background, such as the banners, where a global
    threshold does not; the motion keeps the spots that are moving, not the lines and the boards.
    """
    height, width = current.shape[:2]
    local = cv2.morphologyEx(current, cv2.MORPH_TOPHAT, TOPHAT_KERNEL)
    contrast = cv2.threshold(local, LOCAL_CONTRAST, 255, cv2.THRESH_BINARY)[1]
    moving = cv2.threshold(cv2.absdiff(current, previous), MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
    spots = cv2.bitwise_and(contrast, moving)
    count, labels, stats, centres = cv2.connectedComponentsWithStats(spots)
    found = []
    for label in range(1, count):
        area = int(stats[label][cv2.CC_STAT_AREA])
        if not MIN_AREA <= area <= MAX_AREA:
            continue
        if int(current[labels == label].max()) < MIN_BRIGHTNESS:  # the shuttle is almost white
            continue
        x, y = centres[label]
        found.append((float(x) / width, float(y) / height))
    return drop_clusters(found)


def drop_clusters(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Spots with many neighbours close by are the texture of a shirt or a court line, not a shuttle."""
    kept = []
    for x, y in points:
        neighbours = sum(1 for u, v in points if (u, v) != (x, y) and np.hypot(u - x, v - y) <= CLUSTER_RADIUS)
        if neighbours < CLUSTER_LIMIT:
            kept.append((x, y))
    return kept


def step(tracks: tuple[Track, ...], candidates: list[tuple[float, float]], frame_index: int) -> tuple[Track, ...]:
    """The tracks after one frame: extended where a candidate fits, started where none fits, and old ones dropped."""
    pairs = sorted(
        (distance, track_index, cand_index)
        for track_index, track in enumerate(tracks)
        for cand_index, candidate in enumerate(candidates)
        if (distance := float(np.hypot(*(np.subtract(candidate, track.predicted(frame_index)))))) <= GATE
    )
    extended: dict[int, tuple[float, float]] = {}
    taken: set[int] = set()
    for _, track_index, cand_index in pairs:
        if track_index in extended or cand_index in taken:
            continue
        extended[track_index] = candidates[cand_index]
        taken.add(cand_index)
    updated = [
        Track(track.points + ((frame_index, *extended[index]),)) if index in extended else track
        for index, track in enumerate(tracks)
    ]
    started = [Track(((frame_index, x, y),)) for index, (x, y) in enumerate(candidates) if index not in taken]
    alive = [track for track in updated + started if frame_index - track.last()[0] <= FORGET_FRAMES]
    return tuple(alive)


def straightness(track: Track) -> float:
    """The distance from the first to the last of the last points, over the path walked: 1.0 is a straight line."""
    recent = track.points[-STRAIGHT_POINTS:]
    walked = sum(
        float(np.hypot(b[1] - a[1], b[2] - a[2])) for a, b in zip(recent, recent[1:])
    )
    if walked == 0:
        return 0.0
    return float(np.hypot(recent[-1][1] - recent[0][1], recent[-1][2] - recent[0][2])) / walked


def follow(
    tracks: tuple[Track, ...], frame_index: int, chosen: Track | None
) -> tuple[tuple[float, float] | None, Track | None]:
    """The shuttle at this frame and the track it belongs to.

    The track chosen before is kept while it is still recent and straight, so the shuttle is followed instead of
    jumping between tracks. Only when it is lost is the longest recent straight track chosen.
    """
    recent = [
        track for track in tracks
        if len(track.points) >= MIN_TRACK_POINTS and frame_index - track.last()[0] <= MAX_MISS_FRAMES
        and straightness(track) >= MIN_STRAIGHTNESS
    ]
    if not recent:
        return None, None
    kept = [track for track in recent if chosen is not None and track.points[0] == chosen.points[0]]
    best = kept[0] if kept else max(recent, key=lambda track: (len(track.points), track.last()[0]))
    _, x, y = best.last()
    return (x, y), best


def shuttle_at(tracks: tuple[Track, ...], frame_index: int) -> tuple[float, float] | None:
    """The shuttle at this frame, without the memory of the track followed before."""
    position, _ = follow(tracks, frame_index, None)
    return position
