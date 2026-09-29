"""
Overlay snap links (UX-12, UIUX 10.2).

A link is a promise that a point the user drew stays attached to whatever it
was snapped to. Keeping that promise needs one decision above all others:
**links store IDs, never indices**. An index-based link jumps the moment a path
is inserted anywhere before it, and a painted area that moves by itself is
worse than one that visibly breaks.

Two more rules shape everything here:

* **Links flow one way.** A relief path never depends on the overlay, so
  painting over a model cannot change the model.
* **A lost source breaks loudly.** The link holds its last position, says
  ``C501``, and the region stays. Guessing a replacement would move a painted
  area without anyone asking, and an area that quietly disappeared would leave
  the user with a hole they did not cut.
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

#: The code the spec names for a link whose source is gone.
BROKEN_CODE = "C501"

#: The kinds of link the spec lists, and what each one holds onto.
KINDS = ("anchor", "midpoint", "on_curve", "intersection", "groove_edge",
         "follow")


@dataclass
class Link:
    """One point attached to one piece of relief geometry."""

    kind: str
    path_id: str
    link_id: str = ""
    anchor_id: str = ""
    segment: int = 0
    t: float = 0.0
    other_path_id: str = ""
    index: int = 0
    side: str = ""
    branch: int = 0
    end_a: str = ""
    end_b: str = ""
    last_point_mm: np.ndarray = field(default_factory=lambda: np.zeros(2))
    broken: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.kind!r} is not a kind of link; "
                             f"expected one of {KINDS}")
        self.last_point_mm = np.asarray(self.last_point_mm,
                                        dtype=np.float64).ravel()[:2].copy()
        if not self.link_id:
            self.link_id = uuid.uuid4().hex

    @property
    def code(self) -> str:
        return BROKEN_CODE if self.broken else ""

    @property
    def message(self) -> str:
        if not self.broken:
            return f"{self.kind} link on {self.path_id or self.other_path_id}"
        return (f"{BROKEN_CODE}: the {self.kind} link's source "
                f"'{self.path_id or self.other_path_id}' is gone, so this point "
                f"kept the last place it was")

    def hold(self, point) -> "Link":
        """Remember where this link currently sits, for a broken one to keep."""
        self.last_point_mm = np.asarray(point, dtype=np.float64).ravel()[:2].copy()
        return self


def anchor(path_id: str, anchor_id: str) -> Link:
    """A link to a named anchor, which follows the anchor itself."""
    return Link(kind="anchor", path_id=path_id, anchor_id=anchor_id)


def midpoint(path_id: str, segment: int = 0) -> Link:
    """A link that is always the middle of one segment."""
    return Link(kind="midpoint", path_id=path_id, segment=int(segment))


def on_curve(path_id: str, t: float) -> Link:
    """A link holding a fraction along a path, so it survives the path changing."""
    if not 0.0 <= float(t) <= 1.0:
        raise ValueError(f"a fraction along a path runs from 0 to 1, got {t}")
    return Link(kind="on_curve", path_id=path_id, t=float(t))


def intersection(first_path: str, second_path: str, index: int = 0) -> Link:
    """A link to where two paths cross, recomputed whenever either moves."""
    return Link(kind="intersection", path_id=first_path,
                other_path_id=second_path, index=int(index))


def groove_edge(path_id: str, t: float, side: str) -> Link:
    """A link to one side of a groove mouth, which follows the mouth."""
    if side not in ("left", "right"):
        raise ValueError(f"a groove has two sides, got {side!r}")
    return Link(kind="groove_edge", path_id=path_id, t=float(t), side=side)


def follow_segment(path_id: str, t_a: float, t_b: float = None, branch: int = 0) -> Link:
    """A link to the run *between* two points on one path."""
    if t_b is None:
        raise ValueError("a following segment needs two ends, not one")
    return Link(kind="follow", path_id=path_id, t=float(t_a), side=str(t_b),
                branch=int(branch))


class LinkTable:
    """Every link on one design, and where each of them currently points."""

    def __init__(self) -> None:
        self._links: Dict[str, Link] = {}
        self._points: Dict[str, np.ndarray] = {}

    def add(self, link: Link) -> Link:
        self._links[link.link_id] = link
        self._points.setdefault(link.link_id, link.last_point_mm.copy())
        return link

    def get(self, link_id: str) -> Optional[Link]:
        return self._links.get(link_id)

    def all(self) -> List[Link]:
        return list(self._links.values())

    def points_of(self, link_id: str) -> np.ndarray:
        """Where a link currently sits, as a one-row array."""
        return np.asarray(self._points.get(
            link_id, np.zeros(2)), dtype=np.float64).reshape(1, 2)

    def detach(self, link_id: str) -> bool:
        """Make a link free rather than repair it, which is the user's choice."""
        if link_id not in self._links:
            return False
        del self._links[link_id]
        self._points.pop(link_id, None)
        return True

    def is_broken(self, link_id: str) -> bool:
        link = self._links.get(link_id)
        return bool(link and link.broken)

    def broken_links(self) -> List[Link]:
        return [link for link in self._links.values() if link.broken]

    def resolve(self, paths: Dict[str, dict]) -> None:
        """Re-point every link against the current relief geometry.

        A link whose source is still there moves to where the source says. One
        whose source is gone keeps its last position and is reported; the point
        is never moved to a guess.
        """
        for link in self._links.values():
            found = self._locate(link, paths)
            if found is None:
                link.broken = True
                link.reason = "the source is gone"
                self._points[link.link_id] = link.last_point_mm.copy()
                continue
            link.broken = False
            link.reason = ""
            link.hold(found)
            self._points[link.link_id] = link.hold(found).last_point_mm.copy()

    def _locate(self, link: Link, paths: Dict[str, dict]) -> Optional[np.ndarray]:
        source = paths.get(link.path_id)
        if source is None:
            return None

        if link.kind in ("intersection", "follow"):
            other = paths.get(link.other_path_id) if link.kind == "intersection" else source
            if other is None:
                return None
            if link.kind == "follow":
                return _point_at(source["points"], link.t)
            return _crossing(source["points"], other["points"], link.index)

        points = np.asarray(source["points"], dtype=np.float64).reshape(-1, 2)
        if link.kind == "on_curve" or link.kind == "groove_edge":
            return _point_at(points, link.t)
        if link.kind == "midpoint":
            index = max(0, min(int(link.segment), len(points) - 2))
            return (points[index] + points[index + 1]) * 0.5
        anchors = source.get("anchors", {})
        found = anchors.get(link.anchor_id)
        return None if found is None else np.asarray(found, dtype=np.float64)


def _point_at(points: np.ndarray, t: float) -> np.ndarray:
    """A point a fraction of the way along a run, by arc length."""
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(data) == 1:
        return data[0].copy()
    lengths = np.linalg.norm(np.diff(data, axis=0), axis=1)
    total = float(lengths.sum())
    if total == 0.0:
        return data[0].copy()
    walked = np.concatenate([[0.0], np.cumsum(lengths)])
    wanted = float(np.clip(t, 0.0, 1.0)) * total
    index = int(np.searchsorted(walked, wanted, side="right")) - 1
    index = max(0, min(index, len(data) - 2))
    span = lengths[index]
    if span <= 0.0:
        return data[index].copy()
    ratio = (wanted - walked[index]) / span
    return data[index] + ratio * (data[index + 1] - data[index])


def _crossing(first: np.ndarray, second: np.ndarray, index: int) -> Optional[np.ndarray]:
    """The nth place two runs cross, or None when they do not cross."""
    left = np.asarray(first, dtype=np.float64).reshape(-1, 2)
    right = np.asarray(second, dtype=np.float64).reshape(-1, 2)
    found = []
    for a in range(len(left) - 1):
        for b in range(len(right) - 1):
            hit = _segment_crossing(left[a], left[a + 1], right[b], right[b + 1])
            if hit is not None:
                found.append(hit)
    if not found:
        return None
    return found[min(int(index), len(found) - 1)]


def _segment_crossing(p1, p2, p3, p4):
    """Where two segments meet, or None."""
    r = p2 - p1
    s = p4 - p3
    denominator = r[0] * s[1] - r[1] * s[0]
    if abs(denominator) < 1e-12:
        return None
    difference = p3 - p1
    t = (difference[0] * s[1] - difference[1] * s[0]) / denominator
    u = (difference[0] * r[1] - difference[1] * r[0]) / denominator
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return p1 + t * r
    return None


__all__ = ("BROKEN_CODE", "KINDS", "Link", "LinkTable", "anchor", "follow_segment",
           "groove_edge", "intersection", "midpoint", "on_curve")
