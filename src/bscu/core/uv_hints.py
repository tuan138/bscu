"""
Brush hints for the Tab 2 grid (UX-5, UIUX 3B.3).

The brushes never touch UV. They write four per-face hints, and the solver reads
them back every time a layout is produced:

``density``
    How much UV area this face wants. The expand and shrink brushes move it.
``pin``
    Hold this face's shape and place when the layout is rebuilt.
``priority``
    Zero keeps size, one keeps shape. The priority brush sets it.
``direction``
    The U direction this face would like. The direction brush sets it.

Because the hints live on faces and not on the layout, editing a seam does not
discard them: a face keeps its hint whichever chart it ends up in. The one
thing that can genuinely break is a seam running through a pinned region, and
:func:`split_pins` exists to say so out loud rather than quietly half-unlocking
it.
"""

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

#: Density is clamped to this range; zero would collapse the face to nothing.
MIN_DENSITY = 0.05
MAX_DENSITY = 20.0

#: The brushes a stroke can apply, and whether they add up or overwrite.
ADDITIVE = ("expand", "shrink", "density")
REPLACEABLE = ("pin", "priority", "direction")


@dataclass
class BrushHints:
    """Per-face hints, one entry per face, in face order."""

    faces: np.ndarray
    density: np.ndarray
    pin: np.ndarray
    priority: np.ndarray
    direction: np.ndarray

    def copy(self) -> "BrushHints":
        """An independent copy, for Undo and for the solver's linearisation."""
        return BrushHints(
            faces=self.faces.copy(),
            density=self.density.copy(),
            pin=self.pin.copy(),
            priority=self.priority.copy(),
            direction=self.direction.copy(),
        )

    def to_arrays(self) -> tuple:
        """The four hint arrays, ready to become mesh attributes."""
        return (self.density, self.pin, self.priority, self.direction)

    @classmethod
    def from_arrays(cls, density, pin, priority, direction, face_count: int) -> "BrushHints":
        """Rebuild from mesh attributes, filling in neutral values.

        A mesh that has never been painted has no attributes at all, and a mesh
        saved by an older version may have some but not all. Missing hints come
        back neutral instead of raising, so an old file still opens.
        """
        empty = np.asarray(density).size == 0
        if empty:
            density = np.ones(face_count, dtype=np.float64)
            pin = np.zeros(face_count, dtype=bool)
            priority = np.zeros(face_count, dtype=np.float64)
            direction = np.zeros((face_count, 2), dtype=np.float64)
        return cls(
            faces=np.zeros((face_count, 3), dtype=np.int64),
            density=np.asarray(density, dtype=np.float64).ravel(),
            pin=np.asarray(pin, dtype=bool).ravel(),
            priority=np.asarray(priority, dtype=np.float64).ravel(),
            direction=np.asarray(direction, dtype=np.float64).reshape(-1, 2),
        )


def paint(hints: BrushHints, mask: np.ndarray, kind: str, strength: float = 1.0,
          direction=None) -> int:
    """Apply one brush stroke to the masked faces and report how many moved."""
    if kind not in ADDITIVE and kind not in REPLACEABLE:
        raise ValueError(f"unknown brush {kind!r}; expected one of "
                         f"{ADDITIVE + REPLACEABLE}")
    selected = np.asarray(mask, dtype=bool).ravel()
    if selected.size != len(hints.density):
        raise ValueError(
            f"mask covers {selected.size} faces but the hints cover {len(hints.density)}"
        )
    if not selected.any():
        return 0

    if kind in ADDITIVE:
        if kind == "expand":
            hints.density[selected] *= (1.0 + strength)
        elif kind == "shrink":
            hints.density[selected] /= (1.0 + strength)
        else:
            hints.density[selected] = strength
        np.clip(hints.density, MIN_DENSITY, MAX_DENSITY, out=hints.density)
    elif kind == "pin":
        hints.pin[selected] = strength > 0.0
    elif kind == "priority":
        hints.priority[selected] = float(np.clip(strength, 0.0, 1.0))
    else:
        if direction is None:
            raise ValueError("the direction brush needs a direction")
        vector = np.asarray(direction, dtype=np.float64).ravel()
        length = float(np.linalg.norm(vector))
        if length == 0.0:
            raise ValueError("a direction brush with a zero length vector has no direction")
        hints.direction[selected] = vector / length

    return int(selected.sum())


def neighbour_pairs(faces: np.ndarray) -> np.ndarray:
    """Every pair of faces that share an edge, as (F, 2) rows.

    Relaxation runs on this, and it is built with one sort rather than a
    dictionary per face, because a hundred thousand faces is a normal chart.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return np.zeros((0, 2), dtype=np.int64)
    first = np.sort(np.stack([tris[:, 0], tris[:, 1]], axis=1), axis=1)
    second = np.sort(np.stack([tris[:, 1], tris[:, 2]], axis=1), axis=1)
    third = np.sort(np.stack([tris[:, 2], tris[:, 0]], axis=1), axis=1)
    edges = np.concatenate([first, second, third], axis=0)

    owner = np.tile(np.arange(tris.shape[0]), 3)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owner = edges[order], owner[order]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    left, right = owner[:-1][same], owner[1:][same]
    unique = left != right
    return np.stack([left[unique], right[unique]], axis=1)


def relax(hints: BrushHints, pairs: np.ndarray, passes: int = 1,
          strength: float = 0.5) -> int:
    """Soften painted density, easing each face towards its neighbours.

    The pin marker is a decision, not a value, so relaxation leaves it alone.
    """
    links = np.asarray(pairs, dtype=np.int64).reshape(-1, 2)
    if not links.size or passes <= 0:
        return 0
    count = len(hints.density)
    degree = np.bincount(links.ravel(), minlength=count).astype(np.float64)
    np.maximum(degree, 1.0, out=degree)

    moved = 0
    for _ in range(passes):
        before = hints.density.copy()
        neighbour_mean = (np.bincount(links[:, 0], weights=hints.density[links[:, 1]],
                                      minlength=count)
                          + np.bincount(links[:, 1], weights=hints.density[links[:, 0]],
                                        minlength=count))
        # Unpainted faces drift back to neutral instead of averaging forever.
        target = np.where(hints.pin, hints.density, neighbour_mean / degree)
        hints.density += (target - hints.density) * strength
        np.clip(hints.density, MIN_DENSITY, MAX_DENSITY, out=hints.density)
        moved = max(moved, int(np.count_nonzero(np.abs(hints.density - before) > 1e-9)))
    return moved


def split_pins(hints: BrushHints, island_ids: np.ndarray) -> List[np.ndarray]:
    """Pinned regions that a seam has cut in two, as lists of face indices.

    A pinned region is a run of connected pinned faces. A run that now spans
    more than one island cannot be honoured as a single decision, so each piece
    is reported and the user gets to look at it.
    """
    islands = np.asarray(island_ids, dtype=np.int64).ravel()
    if islands.size != len(hints.pin):
        raise ValueError(
            f"got island ids for {islands.size} faces but {len(hints.pin)} hints"
        )
    links = neighbour_pairs(hints.faces)
    parent = {int(face): int(face) for face in np.flatnonzero(hints.pin)}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    pinned = set(parent)
    for left, right in links:
        if int(left) in pinned and int(right) in pinned:
            a, b = find(int(left)), find(int(right))
            if a != b:
                parent[a] = b

    groups: dict = {}
    for face in parent:
        groups.setdefault(find(face), []).append(face)
    return [
        np.asarray(sorted(members), dtype=np.int64)
        for members in groups.values()
        if len({int(islands[face]) for face in members}) > 1
    ]


def priority_weights(hints: BrushHints) -> np.ndarray:
    """Per-face blend between keep-size and keep-shape, for the chart solver.

    A face at priority 1 is held to its shape, a face at 0 is happy to change
    area, and the slider in the panel moves the global balance on top of this.
    """
    return np.clip(1.0 - np.asarray(hints.priority, dtype=np.float64).ravel(), 0.0, 1.0)


def blend_for(hints: BrushHints, global_blend: float) -> np.ndarray:
    """The per-face keep-shape fraction after the global slider is applied."""
    return np.clip(global_blend * (0.5 + priority_weights(hints)), 0.0, 1.0)


def pin_pairs(hints: BrushHints) -> Tuple[Tuple[int, int], ...]:
    """Two pinned vertices per chart, chosen as far apart as possible.

    A conformal system has four free degrees of freedom and two vertices close
    them, so picking the two ends of the chart keeps the conditioning sane.
    """
    pinned = np.flatnonzero(hints.pin)
    if pinned.size >= 2:
        return (int(pinned[0]), int(pinned[-1]))
    return (0, max(1, len(hints.density) - 1))
