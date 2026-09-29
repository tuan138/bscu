"""
One-dimensional cross-section profiles (UX-10, UIUX 5.5, 5.12).

A profile turns a distance from a path into a depth. The same small set of
operations covers everything the panels expose - a V cut, a flat-bottomed
channel, a rounded wall, a knife edge, a curve the user drew - and they compose,
so a wall can be rounded and then capped without either operation knowing about
the other.

Everything is in millimetres. Blender works in metres internally, and letting
a factor of a thousand leak into a depth is how a 2 mm cut becomes a 2 m one.
"""

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

#: Depths are clamped to this, so a mis-typed number cannot cut through a part.
MAX_DEPTH_MM = 1e4


@dataclass(frozen=True)
class Profile:
    """A cross-section: distance in, depth out, both in millimetres."""

    name: str
    depth_mm: Callable[[np.ndarray], np.ndarray]
    max_slope: float = math.inf

    def evaluate(self, distance_mm: np.ndarray) -> np.ndarray:
        """Depth removed at each distance from the path, negative going down.

        The distance is unsigned and measured out from the path, so a profile is
        one-sided by construction: past the point where the profile reaches zero
        there is no cut, and nothing happens on any other side of the line.
        """
        distance = np.maximum(np.asarray(distance_mm, dtype=np.float64).ravel(), 0.0)
        depth = np.asarray(self.depth_mm(distance), dtype=np.float64).ravel()
        return -np.clip(depth, 0.0, MAX_DEPTH_MM)


def vee(depth_mm: float, angle_deg: float) -> Profile:
    """A plain V cut, the shape a ball nose leaves in a single pass."""
    half_angle = math.radians(max(min(angle_deg, 89.99), 0.01))
    slope = math.tan(half_angle)
    reach = abs(depth_mm) / slope

    def depth(distance: np.ndarray) -> np.ndarray:
        return np.where(distance <= reach,
                        np.maximum(depth_mm - distance * slope, 0.0), 0.0)

    return Profile(f"vee{angle_deg:g}", depth, slope)


def flat(depth_mm: float, width_mm: float) -> Profile:
    """A channel with a flat bottom and vertical walls."""
    half = abs(width_mm) * 0.5

    def depth(distance: np.ndarray) -> np.ndarray:
        return np.where(distance <= half, depth_mm, 0.0)

    return Profile(f"flat{width_mm:g}", depth)


def fillet(depth_mm: float, radius_mm: float) -> Profile:
    """A quarter-round wall, as a ball nose of that radius would leave."""
    radius = abs(radius_mm)

    def depth(distance: np.ndarray) -> np.ndarray:
        if radius == 0.0:
            return np.zeros_like(distance)
        round_part = np.sqrt(np.maximum(radius * radius - distance * distance, 0.0))
        return np.where(distance <= radius, round_part * depth_mm / radius, 0.0)

    return Profile(f"fillet{radius_mm:g}", depth, 0.0 if radius == 0.0 else None)


def ramp(depth_mm: float, run_mm: float) -> Profile:
    """A straight wall leaning away from the path."""
    slope = abs(depth_mm) / abs(run_mm) if run_mm else math.inf
    reach = abs(run_mm)

    def depth(distance: np.ndarray) -> np.ndarray:
        return np.where(distance <= reach,
                        np.maximum(depth_mm - distance * slope, 0.0), 0.0)

    return Profile(f"ramp{run_mm:g}", depth, slope)


def blend(first: Profile, second: Profile, amount: float) -> Profile:
    """Mix two profiles, for a wall that is part V and part flat."""
    share = float(np.clip(amount, 0.0, 1.0))

    def depth(distance: np.ndarray) -> np.ndarray:
        return first.depth_mm(distance) * (1.0 - share) + \
            second.depth_mm(distance) * share

    return Profile(f"{first.name}+{second.name}", depth,
                   max(first.max_slope, second.max_slope))


def mirror_max(profiles: Sequence[Profile]) -> Profile:
    """The deepest of several profiles, which is how stacked effects combine."""
    if not profiles:
        raise ValueError("nothing to combine")
    depth = lambda distance: np.maximum.reduce(  # noqa: E731
        [profile.depth_mm(distance) for profile in profiles])
    return Profile("deepest", depth,
                   max(profile.max_slope for profile in profiles))


def from_curve(points: Sequence, depth_mm: float) -> Profile:
    """A profile the user drew, as a monotone table of (distance, fraction).

    The fraction is how deep the cut is at that distance out from the path, with
    1 meaning the full depth at the path itself and 0 meaning the untouched
    surface.

    A profile that doubles back on itself is refused rather than quietly
    sampled: a table that goes back up would make the cut thinner in the middle
    than at its edge, and no cutter does that.
    """
    table = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(table) < 2:
        raise ValueError("a drawn profile needs at least two points")
    distances = table[:, 0]
    if np.any(np.diff(distances) <= 0.0):
        raise ValueError("a drawn profile must move outwards, not back on itself")
    if np.any(table[:, 1] < 0.0) or np.any(table[:, 1] > 1.0):
        raise ValueError("a drawn profile's fraction must sit between 0 and 1")
    return Profile("drawn", _tabulated(table, float(depth_mm)))


def _tabulated(table: np.ndarray, depth_mm: float) -> Callable[[np.ndarray], np.ndarray]:
    def depth(distance: np.ndarray) -> np.ndarray:
        # A fraction of 1 is the full depth, at the path; 0 is the surface.
        fraction = np.interp(distance, table[:, 0], table[:, 1],
                             left=table[0, 1], right=0.0)
        return fraction * depth_mm

    return depth


__all__ = (
    "MAX_DEPTH_MM",
    "Profile",
    "blend",
    "fillet",
    "flat",
    "from_curve",
    "mirror_max",
    "ramp",
    "vee",
)
