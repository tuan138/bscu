"""
Canvas geometry primitives (UX-9b, UIUX 5.3).

The flat space the user draws in, in millimetres. Everything here is a value:
constructing a line does not register it anywhere, and moving a corner produces
a new geometry rather than editing one, so a drawing can be re-solved from its
source data instead of being patched in place. That is what keeps an edit and
its derived region inside one undo step.
"""

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np

Point = Tuple[float, float]


def as_point(value) -> np.ndarray:
    """A canvas point as a length-two numpy array."""
    data = np.asarray(value, dtype=np.float64).ravel()
    if data.size < 2:
        raise ValueError(f"a canvas point needs two coordinates, got {data.size}")
    return data[:2].copy()


def polyline_length(points) -> float:
    """Total length of a run of points, in millimetres."""
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(data) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(data, axis=0), axis=1).sum())


@dataclass(frozen=True)
class Line:
    """A straight run between two canvas points."""

    start: np.ndarray
    end: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", as_point(self.start))
        object.__setattr__(self, "end", as_point(self.end))

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.end - self.start))

    @property
    def direction(self) -> np.ndarray:
        """The unit vector along the line, pointing from start to end."""
        span = self.end - self.start
        norm = np.linalg.norm(span)
        if norm == 0.0:
            raise ValueError("a line of no length has no direction")
        return span / norm

    def point_at(self, distance: float) -> np.ndarray:
        """A point a given distance along from the start."""
        if self.length == 0.0:
            return self.start.copy()
        return self.start + unit_span(self.end - self.start) * distance

    def closest(self, points) -> np.ndarray:
        """The nearest point on the *segment* for each of several points."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        span = self.end - self.start
        length = float(np.linalg.norm(span))
        if length == 0.0:
            return np.repeat(self.start[None, :], len(data), axis=0)
        offset = data - self.start
        along = np.clip((offset @ span) / (length * length), 0.0, 1.0)
        return self.start + along[:, None] * span

    def distance(self, points) -> np.ndarray:
        """Distance from each point to this segment."""
        return np.linalg.norm(
            np.asarray(points, dtype=np.float64).reshape(-1, 2) - self.closest(points),
            axis=1)

    def reversed(self) -> "Line":
        return Line(self.end, self.start)

    def endpoints(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.start, self.end


@dataclass(frozen=True)
class Arc:
    """A circular arc, swept from ``start_deg`` to ``end_deg``."""

    centre: np.ndarray
    radius: float
    start_deg: float
    end_deg: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "centre", as_point(self.centre))
        if self.radius < 0.0:
            raise ValueError(f"a radius cannot be negative, got {self.radius}")

    @property
    def sweep_deg(self) -> float:
        """How far the arc goes, always counted as a positive turn."""
        return abs(self.end_deg - self.start_deg)

    @property
    def length(self) -> float:
        return math.radians(self.sweep_deg) * self.radius

    def point_at(self, angle_deg: float) -> np.ndarray:
        angle = math.radians(angle_deg)
        return self.centre + self.radius * np.array([math.cos(angle),
                                                     math.sin(angle)])

    @property
    def start(self) -> np.ndarray:
        return self.point_at(self.start_deg)

    @property
    def end(self) -> np.ndarray:
        return self.point_at(self.end_deg)

    def sample(self, steps: int = 32) -> np.ndarray:
        """Points along the arc, in the direction it was drawn."""
        angles = np.linspace(self.start_deg, self.end_deg, max(2, steps))
        return np.asarray([self.point_at(angle) for angle in angles])

    def endpoints(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.start, self.end

    def reversed(self) -> "Arc":
        return Arc(self.centre, self.radius, self.end_deg, self.start_deg)

    def length_of(self) -> float:
        return self.length


def unit_span(span: np.ndarray) -> np.ndarray:
    """A direction as a unit vector, or a zero vector for a zero span."""
    norm = float(np.linalg.norm(span))
    return span / norm if norm else np.zeros(2, dtype=np.float64)


def cubic_bezier(start, first, second, end, steps: int = 64) -> np.ndarray:
    """Sample a cubic Bezier, clamped to the box its control points describe.

    The clamp is what keeps a curve from bulging out past a handle the user
    placed. It is a deliberate departure from a textbook Bezier, and the reason
    is that the user can see the handles.
    """
    points = np.asarray([as_point(start), as_point(first), as_point(second),
                         as_point(end)], dtype=np.float64)
    t = np.linspace(0.0, 1.0, max(2, steps))[:, None]
    curve = ((1 - t) ** 3 * points[0] + 3 * (1 - t) ** 2 * t * points[1]
             + 3 * (1 - t) * t ** 2 * points[2] + t ** 3 * points[3])
    low = points.min(axis=0)
    high = points.max(axis=0)
    return np.clip(curve, low, high)


def polyline_to_lines(points) -> list:
    """Turn a run of points into the lines between them."""
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(data) < 2:
        raise ValueError("a run needs at least two points to have a line in it")
    return [Line(data[index], data[index + 1]) for index in range(len(data) - 1)]


def bezier_length(curve) -> float:
    return polyline_length(curve)


def as_sequence(value) -> Sequence:
    return list(value)


__all__ = (
    "Arc",
    "Line",
    "Point",
    "as_point",
    "bezier_length",
    "cubic_bezier",
    "polyline_length",
    "polyline_to_lines",
    "unit_span",
)
