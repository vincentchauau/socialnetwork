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
MIN_BRIGHTNESS = 120  # grey level of the shuttle's centre: nearly white
CLUSTER_RADIUS = 0.04  # share of the frame
CLUSTER_LIMIT = 3  # this many neighbours close by make a cluster
TOPHAT_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
MIN_AREA = 2  # pixels, at the frame's own resolution
MAX_AREA = 30  # the shuttle is a few pixels; a player's white shirt or shoe is bigger
HIT_GATE = 0.04  # a track that changes direction (a hit) may be extended by a candidate this close to its straight-line prediction
GATE = 0.1  # a candidate this far (share of the frame) from a track's prediction can extend it
MAX_MISS_FRAMES = 4  # a track that is not extended for this many frames stops being the shuttle
EDGE_MARGIN = 0.02  # candidates this close to the frame edge are lights or logos, not the shuttle
BOX_MARGIN = 0.02  # a player's box is grown by this share before candidates are dropped
PREDICT_POINTS = 6  # the last points a track is predicted from along its flight path
MIN_TRACK_POINTS = 4  # a track needs this many points before it can be the shuttle
FIT_POINTS = 8  # the points a track must follow a flight path through (for the whole-video choice)
MAX_FIT_RESIDUAL = 0.01  # share of the frame: a shuttle flies a smooth path (a parabola in y, a line in x)
MIN_SHOWN_POINTS = 15  # a shuttle is shown only on a track this long
MIN_GLOBAL_SCORE = 6  # a track needs this many smooth points to be the shuttle in the whole-video choice
FORGET_FRAMES = 16  # a track not extended for this long is dropped
STRAIGHT_POINTS = 6  # the last points that must lie on a straight line
MIN_STRAIGHTNESS = 0.7  # the straight distance over the walked distance: a shuttle flies straight, a limb swings back


@dataclass(frozen=True)
class Track:
    points: tuple[tuple[int, float, float], ...]  # (frame index, x, y)

    def last(self) -> tuple[int, float, float]:
        return self.points[-1]

    def coasted(self, frame_index: int) -> tuple[float, float]:
        """Where the track goes if it keeps its last velocity: the shuttle changes its path at a hit, the parabola does not."""
        frame, x, y = self.last()
        if len(self.points) < 2:
            return x, y
        prev_frame, prev_x, prev_y = self.points[-2]
        steps = frame - prev_frame
        ahead = frame_index - frame
        return x + (x - prev_x) / steps * ahead, y + (y - prev_y) / steps * ahead

    def predicted(self, frame_index: int) -> tuple[float, float]:
        """Where the track should be at this frame: along a flight path (a line in x, a parabola in y) through its last points.

        With fewer than four points there is no curve to fit, so the last velocity is used.
        """
        frame, x, y = self.last()
        if len(self.points) < 4:
            if len(self.points) < 2:
                return x, y
            prev_frame, prev_x, prev_y = self.points[-2]
            steps = frame - prev_frame
            ahead = frame_index - frame
            return x + (x - prev_x) / steps * ahead, y + (y - prev_y) / steps * ahead
        recent = self.points[-PREDICT_POINTS:]
        times = np.array([point[0] for point in recent], dtype=float)
        x_line = np.polyfit(times, [point[1] for point in recent], 1)
        y_curve = np.polyfit(times, [point[2] for point in recent], 2)
        return float(np.polyval(x_line, frame_index)), float(np.polyval(y_curve, frame_index))


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


RING_MAX_STD = 25  # the ring around a shuttle is an even background: its spread is small
RING_MIN_DROP = 40  # and darker than the shuttle's peak by at least this much
STREAK_ENABLED = True  # a fast shuttle is a motion-blur streak: take its leading end
STREAK_ELONGATION = 3.0  # a streak is at least this many times longer than it is wide
MAX_STREAK_AREA = 160  # at the reference width, a streak can be this many pixels
REFERENCE_WIDTH = 640  # the thresholds above were set for frames this wide; wider frames scale the sizes with it


def scaled(value: float, width: int) -> float:
    return value * width / REFERENCE_WIDTH


def find_candidates(previous: NDArray[np.uint8], current: NDArray[np.uint8]) -> list[tuple[float, float]]:
    """Spots that are brighter than their own surroundings and moved since the previous frame, as 0..1 of the frame.

    The local brightness (top-hat) finds a small white spot on a bright background, such as the banners, where a global
    threshold does not; the motion keeps the spots that are moving, not the lines and the boards.
    """
    height, width = current.shape[:2]
    size = max(3, int(round(scaled(9, width))) | 1)  # an odd kernel about the size of the shuttle
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    local = cv2.morphologyEx(current, cv2.MORPH_TOPHAT, kernel)
    contrast = cv2.threshold(local, LOCAL_CONTRAST, 255, cv2.THRESH_BINARY)[1]
    moving = cv2.threshold(cv2.absdiff(current, previous), MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
    spots = cv2.bitwise_and(contrast, moving)
    count, labels, stats, centres = cv2.connectedComponentsWithStats(spots)  # noqa: F841
    found = []
    for label in range(1, count):
        area = int(stats[label][cv2.CC_STAT_AREA])
        if not scaled(MIN_AREA, width) <= area <= scaled(MAX_AREA, width):
            streak = STREAK_ENABLED and area <= scaled(MAX_STREAK_AREA, width)
            if not streak:
                continue
        x0, y0, w_box, h_box = (int(v) for v in stats[label][:4])
        inside = labels[y0:y0 + h_box, x0:x0 + w_box] == label  # only the blob's own box: a full-frame mask is slow
        if int(current[y0:y0 + h_box, x0:x0 + w_box][inside].max()) < MIN_BRIGHTNESS:  # the shuttle is almost white
            continue
        pixels = np.argwhere(inside) + np.array([y0, x0])
        if not isolated(current, x0, y0, w_box, h_box, int(current[y0:y0 + h_box, x0:x0 + w_box][inside].max()), width):
            continue
        point = leading_end(pixels, current) if STREAK_ENABLED and is_streak(pixels) else centres[label]
        x, y = point
        found.append((float(x) / width, float(y) / height))
    return drop_clusters(found)


def is_streak(pixels: NDArray[np.int64]) -> bool:
    """A long, thin blob: the motion blur of a fast shuttle."""
    if len(pixels) < 3:
        return False
    eigenvalues = np.linalg.eigvalsh(np.cov(pixels.T.astype(float)))
    return bool(eigenvalues[1] > 0 and np.sqrt(eigenvalues[1] / max(eigenvalues[0], 1e-6)) >= STREAK_ELONGATION)


def leading_end(pixels: NDArray[np.int64], current: NDArray[np.uint8]) -> tuple[float, float]:
    """The brighter end of a streak along its long axis: the shuttle is at its leading, brighter end."""
    centre = pixels.mean(axis=0)
    axis = np.linalg.eigh(np.cov(pixels.T.astype(float)))[1][:, 1]
    along = (pixels - centre) @ axis
    low, high = pixels[np.argmin(along)], pixels[np.argmax(along)]
    brightness_low = int(current[low[0], low[1]])
    brightness_high = int(current[high[0], high[1]])
    end = high if brightness_high >= brightness_low else low
    return float(end[1]), float(end[0])


def drop_clusters(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Spots with many neighbours close by are the texture of a shirt or a court line, not a shuttle."""
    kept = []
    for x, y in points:
        neighbours = sum(1 for u, v in points if (u, v) != (x, y) and np.hypot(u - x, v - y) <= CLUSTER_RADIUS)
        if neighbours < CLUSTER_LIMIT:
            kept.append((x, y))
    return kept


def step(
    tracks: tuple[Track, ...],
    candidates: list[tuple[float, float]],
    frame_index: int,
) -> tuple[Track, ...]:
    """The tracks after one frame: extended where a candidate fits, started where none fits, and old ones dropped."""
    predictions = [track.predicted(frame_index) for track in tracks]  # once per track, not once per candidate
    coasts = [track.coasted(frame_index) for track in tracks]
    cand = np.asarray(candidates, dtype=float).reshape(-1, 2)
    pairs = []
    for track_index, (predicted, coasted) in enumerate(zip(predictions, coasts)):
        if cand.shape[0] == 0:
            break
        near = np.hypot(*(cand - predicted).T)
        coast = np.hypot(*(cand - coasted).T)
        for cand_index in np.flatnonzero((near <= GATE) | (coast <= HIT_GATE)):
            distance = near[cand_index] if near[cand_index] <= GATE else coast[cand_index]
            pairs.append((float(distance), track_index, int(cand_index)))
    pairs.sort()
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


def fit_residual(track: Track, window: int = FIT_POINTS) -> float:
    """Root-mean-square distance of the last points from a flight path: a line in x and a parabola in y (gravity)."""
    recent = track.points[-window:]
    if len(recent) < MIN_TRACK_POINTS:
        return float("inf")
    times = np.array([point[0] for point in recent], dtype=float)
    xs = np.array([point[1] for point in recent])
    ys = np.array([point[2] for point in recent])
    x_fit = np.polyval(np.polyfit(times, xs, 1), times)
    y_fit = np.polyval(np.polyfit(times, ys, 2), times)
    return float(np.sqrt(np.mean((xs - x_fit) ** 2 + (ys - y_fit) ** 2)))


def local_fit_score(track: Track, window: int = FIT_POINTS) -> int:
    """How many points of the track lie on a flight path with their neighbours: a long, smooth path scores high."""
    score = 0
    for index in range(len(track.points)):
        around = Track(track.points[max(0, index - window // 2): index + window // 2 + 1])
        if fit_residual(around, len(around.points)) <= MAX_FIT_RESIDUAL:
            score += 1
    return score


def archive_update(archive: dict[tuple[int, float, float], Track], tracks: tuple[Track, ...]) -> dict[tuple[int, float, float], Track]:
    """Keeps the longest version of every track seen in the video, keyed by where it starts."""
    for track in tracks:
        key = track.points[0]
        if key not in archive or len(track.points) > len(archive[key].points):
            archive[key] = track
    return archive


def position_on(track: Track, frame_index: int) -> tuple[float, float] | None:
    """The track's position at this frame, interpolated between its points; None when it has no point nearby."""
    for (f1, x1, y1), (f2, x2, y2) in zip(track.points, track.points[1:]):
        if f1 <= frame_index <= f2:
            share = 0.0 if f2 == f1 else (frame_index - f1) / (f2 - f1)
            return x1 + (x2 - x1) * share, y1 + (y2 - y1) * share
    return None


def global_positions(archive: dict[tuple[int, float, float], Track], frame_count: int) -> list[tuple[float, float] | None]:
    """The shuttle on every frame: the best-scoring tracks of the whole video claim their frames first.

    A track is judged on all its points, not on the frames before one moment, so a limb that moves smoothly for a
    short while does not beat the shuttle that flies along the whole path.
    """
    ranked = sorted(archive.values(), key=lambda track: (local_fit_score(track), len(track.points)), reverse=True)
    positions: list[tuple[float, float] | None] = [None] * frame_count
    claimed = [False] * frame_count
    for track in ranked:
        if local_fit_score(track) < MIN_GLOBAL_SCORE or len(track.points) < MIN_SHOWN_POINTS:  # short tracks are not shown
            continue
        for frame_index in range(track.points[0][0], min(track.points[-1][0], frame_count - 1) + 1):
            if claimed[frame_index]:
                continue
            position = position_on(track, frame_index)
            if position is not None:
                positions[frame_index] = position
                claimed[frame_index] = True
    return positions


def isolated(frame: NDArray[np.uint8], x0: int, y0: int, w_box: int, h_box: int, peak: int, width: int) -> bool:
    """A shuttle is a white spot on an even background: the ring around it is darker than its peak and does not vary much."""
    margin = max(2, int(round(scaled(3, width))))
    top, left = max(0, y0 - margin), max(0, x0 - margin)
    bottom, right = min(frame.shape[0], y0 + h_box + margin), min(frame.shape[1], x0 + w_box + margin)
    region = frame[top:bottom, left:right].astype(float)
    mask = np.ones(region.shape, dtype=bool)
    mask[y0 - top:y0 - top + h_box, x0 - left:x0 - left + w_box] = False
    ring = region[mask]
    if ring.size == 0:
        return False
    return bool(ring.std() <= RING_MAX_STD and ring.mean() <= peak - RING_MIN_DROP)
