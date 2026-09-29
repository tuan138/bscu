"""
Snapping on the canvas (UX-9a, UIUX 3B.5 and 10.2).

Snapping is a search for the nearest thing worth snapping to, within a
tolerance, and the kinds are the ones the spec's table lists. What makes it more
than a distance search is the second half: a snap to relief geometry is a
*link*, not a coordinate, so the drawn point follows its source when the source
moves. That is why a snap carries a :class:`~bscu.core.overlay_links.Link`
rather than a position.

The tolerance is in screen pixels, because that is what a user can see. It is
converted to millimetres at the point under the cursor, because that is the
space the drawing lives in. The conversion happens once, in
:func:`pixels_to_mm`, so no caller has to remember which space it is holding.
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np

from bscu.core.overlay_links import Link, anchor, intersection, on_curve

#: The snap kinds the canvas offers, in the order they win a tie.
KINDS = ("endpoint", "midpoint", "on_curve", "intersection", "groove_edge")

#: A hit within this many pixels of a candidate counts; beyond it, nothing.
DEFAULT_PIXELS = 12.0


@dataclass
class SnapHit:
    """One thing worth snapping to."""

    kind: str
    point_mm: np.ndarray
    path_id: str
    distance_mm: float
    t: float = 0.0
    segment: int = 0
    other_path_id: str = ""
    index: int = 0

    def link(self) -> Link:
        """The link this snap would create, held by ID rather than by position."""
        if self.kind == "midpoint":
            from bscu.core.overlay_links import midpoint

            return midpoint(self.path_id, self.segment)
        if self.kind == "intersection":
            return intersection(self.path_id, self.other_path_id, self.index)
        if self.kind == "endpoint":
            return anchor(self.path_id, self.path_id)
        return on_curve(self.path_id, self.t)


def pixels_to_mm(pixels: float, mm_per_pixel: float) -> float:
    """A screen tolerance in millimetres, at the point under the cursor."""
    if mm_per_pixel <= 0.0:
        raise ValueError("a scale of zero pixels per millimetre cannot be worked in")
    return abs(float(pixels)) * mm_per_pixel


def find_snap(target_mm, paths: dict, tolerance_mm: float,
              kinds: Sequence[str] = KINDS) -> Optional[SnapHit]:
    """The nearest thing to snap to, or None when nothing is close enough.

    Ties go to the kind listed first, so an endpoint beats a point in the middle
    of a line even when they are the same distance away. That ordering is what
    makes snapping feel predictable rather than arbitrary.
    """
    target = np.asarray(target_mm, dtype=np.float64).ravel()[:2]
    best: Optional[SnapHit] = None

    for kind in kinds:
        found = _search(kind, target, paths, tolerance_mm)
        if found is None:
            continue
        if best is None or found.distance_mm < best.distance_mm - 1e-12:
            best = found
    return best


def _search(kind: str, target: np.ndarray, paths: dict, tolerance: float
            ) -> Optional[SnapHit]:
    for path_id, path in paths.items():
        points = np.asarray(path.get("points", np.zeros((0, 2))),
                            dtype=np.float64).reshape(-1, 2)
        if not points.size:
            continue
        found = _on_one_path(kind, target, points, path_id, tolerance)
        if found is not None:
            return found
    return None


def _on_one_path(kind: str, target: np.ndarray, points: np.ndarray,
                 path_id: str, tolerance: float) -> Optional[SnapHit]:
    if kind == "endpoint":
        distances = np.linalg.norm(points - target, axis=1)
        index = int(np.argmin(distances))
        if distances[index] > tolerance:
            return None
        return SnapHit(kind, points[index], path_id, float(distances[index]),
                       t=_fraction_at(points, index))

    if kind == "midpoint":
        if len(points) < 2:
            return None
        midpoints = (points[:-1] + points[1:]) * 0.5
        distances = np.linalg.norm(midpoints - target, axis=1)
        index = int(np.argmin(distances))
        if distances[index] > tolerance:
            return None
        return SnapHit(kind, midpoints[index], path_id, float(distances[index]),
                       segment=index, t=_fraction_at(points, index + 1))

    # on_curve and groove_edge both hold a fraction along the path.
    total = _length(points)
    if total <= 0.0:
        return None
    steps = max(2, int(total * 2.0))
    fractions = np.linspace(0.0, 1.0, steps)
    sampled = np.asarray([_at(points, fraction) for fraction in fractions])
    distances = np.linalg.norm(sampled - target, axis=1)
    index = int(np.argmin(distances))
    if distances[index] > tolerance:
        return None
    return SnapHit(kind, sampled[index], path_id, float(distances[index]),
                   t=float(fractions[index]))


def _length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def _at(points: np.ndarray, fraction: float) -> np.ndarray:
    """A point a fraction of the way along a run, by arc length."""
    total = _length(points)
    if total == 0.0:
        return points[0]
    walked = np.concatenate([[0.0], np.cumsum(
        np.linalg.norm(np.diff(points, axis=0), axis=1))])
    index = int(np.searchsorted(walked, float(np.clip(fraction, 0.0, 1.0)) * total,
                                side="right")) - 1
    index = max(0, min(index, len(points) - 2))
    span = walked[index + 1] - walked[index]
    if span <= 0.0:
        return points[index]
    ratio = (float(np.clip(fraction, 0.0, 1.0)) * total - walked[index]) / span
    return points[index] + ratio * (points[index + 1] - points[index])


def _fraction_at(points: np.ndarray, index: int) -> float:
    total = _length(points)
    if total <= 0.0 or index <= 0:
        return 0.0
    walked = float(np.linalg.norm(points[:index] - points[0], axis=1).sum())
    return min(1.0, walked / total)


def snap_or_free(target_mm, paths: dict, tolerance_mm: float,
                 allow_link: bool = True) -> Tuple[np.ndarray, Optional[Link]]:
    """Where a point lands, and the link it gets - or none, if Alt was held.

    Releasing with Alt makes a point free. That is the spec's deliberate escape
    hatch from a link the user did not want, so it has to be reachable without
    undoing anything afterwards.
    """
    if not allow_link:
        return np.asarray(target_mm, dtype=np.float64).ravel()[:2].copy(), None
    hit = find_snap(target_mm, paths, tolerance_mm)
    if hit is None:
        return np.asarray(target_mm, dtype=np.float64).ravel()[:2].copy(), None
    return hit.point_mm.copy(), hit.link()


__all__ = ("DEFAULT_PIXELS", "KINDS", "SnapHit", "find_snap", "pixels_to_mm",
           "snap_or_free")
