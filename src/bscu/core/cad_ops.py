"""
The corner and line operations the canvas offers (UX-9b, UIUX 5.3).

Trim, fillet, chamfer and extend, in millimetres, on the value types from
:mod:`bscu.core.geom2d`. Each returns a new result rather than editing anything,
so the drawing's source data stays the single source of truth and one user
action is one undo step.

The rule these all hold to: the new geometry must actually touch what it
replaces. A fillet whose ends float a thousandth of a millimetre off the walls
looks right on screen and leaves a hole in the mesh. Every operation here
therefore either lands exactly on its neighbours or refuses to run.
"""

import math
from dataclasses import dataclass
from typing import Union

import numpy as np

from .geom2d import Arc, Line, as_point, unit_span

Shape = Union[Line, Arc]


@dataclass(frozen=True)
class CornerResult:
    """What a corner operation did to the two arms meeting there."""

    before: Shape
    """The incoming arm, shortened to where the new geometry starts."""

    after: Shape
    """The outgoing arm, shortened to where the new geometry ends."""

    fillet: Shape
    """The new geometry: an arc for a fillet, a line for a chamfer."""

    def pieces(self) -> tuple:
        return (self.before, self.fillet, self.after)


def _arms(before: Line, after: Line, corner) -> tuple:
    """The corner, and a unit direction along each arm.

    The directions come from the arms themselves rather than from the corner.
    At a genuine corner the corner *is* the end of one arm, so a direction taken
    from it would be a zero vector exactly where the geometry is most needed.
    """
    node = as_point(corner)
    into = unit_span(as_point(before.end) - as_point(before.start))
    away = unit_span(as_point(after.end) - as_point(after.start))
    if not np.any(into) or not np.any(away):
        raise ValueError("a corner needs two arms with length in them")
    return node, into, away


def _arm_capacity(before: Line, after: Line, node) -> tuple:
    """How far each arm can give before it runs out."""
    incoming = float(np.linalg.norm(node - as_point(before.start)))
    outgoing = float(np.linalg.norm(as_point(after.end) - node))
    return incoming, outgoing


def fillet_corner(before: Line, after: Line, corner, radius: float) -> CornerResult:
    """Round a corner, leaving the arc tangent to both arms.

    The tangent point on each arm sits a distance ``radius * tan(theta / 2)``
    back from the corner, where ``theta`` is the interior angle. For a right
    angle that is the radius itself, which is the case worth being sure about.
    """
    if radius <= 0.0:
        raise ValueError(f"a fillet needs a positive radius, got {radius}")

    node, into, away = _arms(before, after, corner)
    # The interior angle is between going back along the incoming arm and
    # forward along the outgoing one, not between the two forward directions.
    cos_angle = float(np.clip(np.dot(-into, away), -1.0, 1.0))
    interior = math.acos(cos_angle)
    if interior <= 1e-9 or interior >= math.pi - 1e-9:
        raise ValueError("the two arms are already in line, so there is no "
                         "corner to round")

    setback = radius * math.tan(interior / 2.0)
    incoming_room, outgoing_room = _arm_capacity(before, after, node)
    if setback >= min(incoming_room, outgoing_room):
        raise ValueError(
            f"a radius of {radius:g} mm needs {setback:.3f} mm of arm, but only "
            f"{min(incoming_room, outgoing_room):.3f} mm is there")

    tangent_in = node - into * setback
    tangent_out = node + away * setback
    # Into the material, which is away from the corner along the inside.
    bisector = unit_span(away - into)
    centre = node + bisector * (radius / math.sin(interior / 2.0))

    start_angle = math.degrees(math.atan2(*(tangent_in - centre)[::-1]))
    end_angle = math.degrees(math.atan2(*(tangent_out - centre)[::-1]))
    arc = Arc(centre, radius, start_angle, end_angle)
    # Sweep the short way, which is the side the corner is actually on.
    if arc.sweep_deg > 180.0:
        arc = arc.reversed()

    return CornerResult(Line(before.start, tangent_in),
                        Line(tangent_out, after.end),
                        arc)


def chamfer_corner(before: Line, after: Line, corner, distance: float) -> CornerResult:
    """Cut a corner off with a straight line a given distance along each arm."""
    if distance <= 0.0:
        raise ValueError(f"a chamfer needs a positive distance, got {distance}")

    node, into, away = _arms(before, after, corner)
    incoming_room, outgoing_room = _arm_capacity(before, after, node)
    if distance >= min(incoming_room, outgoing_room):
        raise ValueError(
            f"a chamfer of {distance:g} mm does not fit: only "
            f"{min(incoming_room, outgoing_room):.3f} mm of arm is there")

    cut_in = node - into * distance
    cut_out = node + away * distance
    return CornerResult(Line(before.start, cut_in),
                        Line(cut_out, after.end),
                        Line(cut_in, cut_out))


def trim_line(line: Line, keep_from) -> Line:
    """Cut a line back so it starts at a point.

    Trimming past the far end leaves an empty line rather than a reversed one: a
    line pointing backwards would silently change which side the material is on.
    """
    start = as_point(keep_from)
    end = as_point(line.end)
    if float(np.linalg.norm(start - end)) >= line.length:
        return Line(start, start)
    return Line(start, end)


def extend_line(line: Line, end_distance: float = 0.0,
                start_distance: float = 0.0) -> Line:
    """Push a line's ends out along its own direction, keeping it straight."""
    if end_distance < 0.0 or start_distance < 0.0:
        raise ValueError("extending by a negative distance would shorten the line")
    if line.length == 0.0:
        raise ValueError("a line of no length has nothing to extend along")
    direction = line.direction
    return Line(line.start - direction * start_distance,
                line.end + direction * end_distance)


def connected(arms, tolerance_mm: float = 1e-6) -> bool:
    """Whether a run of shapes actually joins up, endpoints touching.

    A drawing that looks continuous in the viewport can still have its pieces a
    hair apart, and a mesh built from it would not close.
    """
    if not arms:
        return False
    for current, following in zip(arms, arms[1:]):
        first = current.endpoints()[1]
        second = following.endpoints()[0]
        if np.linalg.norm(first - second) > tolerance_mm:
            return False
    return True


__all__ = (
    "CornerResult",
    "chamfer_corner",
    "connected",
    "extend_line",
    "fillet_corner",
    "trim_line",
)
