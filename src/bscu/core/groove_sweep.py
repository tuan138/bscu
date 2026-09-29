"""
The virtual tool sweep (UX-10b, UIUX 5.13).

At every point along a path there is a virtual tool, shaped by the current
cross-section and leaning two ways: a side tilt $\\gamma$ (negative left,
positive right) and a lead-in tilt $\\beta$ (positive towards the far end of the
path). The groove is the *lower envelope* of that swept tool; a ridge is the
upper one. One model therefore handles the two together rather than needing a
separate rule for each.

Three things here are easy to get subtly wrong, so they are stated as rules
rather than left to the arithmetic:

* **A groove is a shape, not an amount to add up.** Two grooves crossing take
  the deeper of the two, never their sum. Summing would put the intersection at
  twice the depth the user asked for, and no cutter would produce that.
* **An undercut is reported, never clamped.** A tilt past half the tool angle
  cannot be cut; the number the user typed is kept and the problem is named, so
  they can see what they asked for and decide.
* **Reversing a path flips both tilt signs.** Walking a path the other way turns
  a left lean into a right one, and getting that wrong mirrors the whole groove.
"""

import math
from dataclasses import dataclass, field
from typing import List, Sequence

import numpy as np

#: Below this a groove has tapered away; used to decide where a channel ends.
TINY_MM = 1e-9


@dataclass
class SweepChannels:
    """The two tilt channels, one value per point along a path."""

    beta: List[float] = field(default_factory=list)
    gamma: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.beta) != len(self.gamma):
            raise ValueError(
                f"the two channels have to be the same length, got "
                f"{len(self.beta)} and {len(self.gamma)}")

    def check_against(self, path) -> None:
        """Make sure there is a value for every point on the path."""
        points = np.asarray(path, dtype=np.float64).reshape(-1, 2)
        if len(self.beta) != len(points):
            raise ValueError(
                f"the path has {len(points)} points but the channels have "
                f"{len(self.beta)}")

    def at(self, index: int) -> tuple:
        return (float(self.beta[index]), float(self.gamma[index]))


def total_tilt_deg(beta_deg: float, gamma_deg: float) -> float:
    """The tilt of the tool edge once both channels act on it.

    The spec's formula: $\\theta = \\arccos(\\cos\\beta \\cos\\gamma)$. A plain
    sum would be wrong the moment both channels are non-zero, and would let a
    combination through that no single-channel check would catch.
    """
    cosine = (math.cos(math.radians(beta_deg)) * math.cos(math.radians(gamma_deg)))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def half_angle_limit(angle_deg: float) -> float:
    """The most a tool may lean and still cut: half its included angle."""
    return abs(float(angle_deg)) * 0.5


@dataclass
class Undercut:
    """A tilt that cannot be cut, reported with the numbers that caused it."""

    undercut: bool
    total_deg: float
    limit_deg: float
    beta_deg: float
    gamma_deg: float
    message: str = ""

    def __bool__(self) -> bool:
        return self.undercut


def undercut_of(beta_deg: float, gamma_deg: float, angle_deg: float) -> Undercut:
    """Whether a tool lean is cuttable, keeping the number either way.

    The values are never adjusted. A clamped lean would produce a toolpath that
    looks fine and cuts a wall the user did not ask for.
    """
    total = total_tilt_deg(beta_deg, gamma_deg)
    limit = half_angle_limit(angle_deg)
    if total <= limit + 1e-9:
        return Undercut(False, total, limit, float(beta_deg), float(gamma_deg),
                        f"leaning {total:.2f} deg is within the "
                        f"{limit:.2f} deg limit")
    return Undercut(True, total, limit, float(beta_deg), float(gamma_deg),
                    f"leaning {total:.2f} deg passes the {limit:.2f} deg limit, "
                    f"so the tool would undercut; the numbers were kept as given")


def groove_half_width(depth_mm: float, angle_deg: float) -> float:
    """Half the width of a V groove of a given depth, in millimetres."""
    half = math.radians(half_angle_limit(angle_deg))
    return abs(float(depth_mm)) * math.tan(half)


def lead_in_offset(depth_mm: float, beta_deg: float) -> float:
    """How far a lead-in tilt shifts the bottom of a groove, in millimetres.

    On a flat base the shift is $d\\tan\\beta$, which is the spec's third
    acceptance case and the one a machinist checks by eye.
    """
    return float(depth_mm) * math.tan(math.radians(beta_deg))


def reverse_path(path, channels: SweepChannels) -> tuple:
    """Walk a path the other way, flipping the sign of both tilts.

    A left lean read backwards is a right lean, so the signs flip with the
    order. The shape of the groove is unchanged; only which end it starts from
    moves.
    """
    points = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    channels.check_against(points)
    flipped = SweepChannels(
        beta=[-value for value in reversed(channels.beta)],
        gamma=[-value for value in reversed(channels.gamma)],
    )
    return points[::-1].copy(), flipped


def combine_grooves(*depths: np.ndarray) -> np.ndarray:
    """Where grooves cross, the deeper one wins. Grooves never add up."""
    return _reduce(np.minimum, depths)


def combine_ridges(*heights: np.ndarray) -> np.ndarray:
    """Where ridges cross, the taller one wins."""
    return _reduce(np.maximum, heights)


def smooth_min(first: np.ndarray, second: np.ndarray, radius: float) -> np.ndarray:
    """Join two fields with a fillet, which is the spec's "blend smoothly" option.

    With no radius this is a plain minimum, because a crease is the default: a
    knife edge is sometimes exactly what is wanted, and rounding it unasked
    would be a decision the user did not make.
    """
    left = np.asarray(first, dtype=np.float64)
    right = np.asarray(second, dtype=np.float64)
    if radius <= 0.0:
        return np.minimum(left, right)
    weight = np.clip(0.5 + 0.5 * (right - left) / radius, 0.0, 1.0)
    return left * weight + right * (1.0 - weight) - radius * weight * (1.0 - weight)


def along_path(path, steps_per_mm: float = 0.25) -> tuple:
    """Sample points evenly along a path, and the distance each one sits at.

    Spacing is in millimetres so the sample density does not change with the
    size of the part; a path measured in samples would be dense on a small part
    and sparse on a large one.
    """
    points = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    if len(points) < 2:
        raise ValueError("a path needs at least two points to follow")
    if steps_per_mm <= 0.0:
        raise ValueError("the sampling step has to be positive")

    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = float(lengths.sum())
    count = max(2, int(total * steps_per_mm) + 1)
    wanted = np.linspace(0.0, total, count)
    walked = np.concatenate([[0.0], np.cumsum(lengths)])
    sampled = np.asarray([
        _point_at(points, walked, lengths, target) for target in wanted
    ])
    return sampled, wanted


def _point_at(points, walked, lengths, target) -> np.ndarray:
    index = int(np.searchsorted(walked, target, side="right")) - 1
    index = max(0, min(index, len(points) - 2))
    span = lengths[index]
    if span <= 0.0:
        return points[index]
    ratio = (target - walked[index]) / span
    return points[index] + ratio * (points[index + 1] - points[index])


def _reduce(operation, fields: Sequence[np.ndarray]) -> np.ndarray:
    if not fields:
        raise ValueError("there is nothing to combine")
    result = np.asarray(fields[0], dtype=np.float64)
    for other in fields[1:]:
        result = operation(result, np.asarray(other, dtype=np.float64))
    return result


def undercuts_along(channels: SweepChannels, angle_deg: float) -> List[int]:
    """Which points along a path lean past what the tool can cut."""
    found = []
    for index in range(len(channels.beta)):
        beta, gamma = channels.at(index)
        if undercut_of(beta, gamma, angle_deg):
            found.append(index)
    return found


__all__ = (
    "SweepChannels",
    "Undercut",
    "along_path",
    "combine_grooves",
    "combine_ridges",
    "groove_half_width",
    "half_angle_limit",
    "lead_in_offset",
    "reverse_path",
    "smooth_min",
    "total_tilt_deg",
    "undercut_of",
    "undercuts_along",
)
