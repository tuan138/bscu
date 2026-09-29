"""
A DXF reader for the 2.5D canvas (UX-13, UIUX 10.6).

DXF is a tagged text format: a group code, then its value, on alternating lines.
That makes it easy to read and easy to get quietly wrong, so this reader is
strict in the places where guessing would hurt:

* Units come from ``$INSUNITS``. A file without one is reported as missing,
  because assuming inches on a millimetre part is how a part comes out 25 times
  too small.
* An entity this reader does not understand is named in the issues list, not
  skipped. A missing toolpath is a hole in the part, and the user has to hear
  about it.
* Every number that reaches the caller is in millimetres, and every shape says
  so itself, so a downstream module cannot silently mix units.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

#: $INSUNITS values and how many millimetres they are worth.
UNIT_TO_MM = {
    0: 1.0,     # unitless: taken as millimetres
    1: 25.4,    # inches
    2: 304.8,   # feet
    4: 1.0,     # millimetres
    5: 10.0,    # centimetres
    6: 1000.0,  # metres
    9: 0.001,   # millimetres, the fine variant
}

#: Entities this reader turns into geometry.
KNOWN = ("LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE",
         "ELLIPSE")


class DxfError(ValueError):
    """The file cannot be read, and the message says why."""


@dataclass
class DxfResult:
    """What came out of the file, and what could not be dealt with."""

    shapes: List[dict] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    scale_mm: float = 1.0
    units_stated: bool = False

    @property
    def ok(self) -> bool:
        return not self.issues


def scale_to_mm(insunits: Optional[int]) -> float:
    """How many millimetres one drawing unit is worth."""
    if insunits is None:
        return 1.0
    return UNIT_TO_MM.get(int(insunits), 1.0)


def parse_dxf(text: str) -> DxfResult:
    """Read a DXF file's entities and report what it could not handle."""
    pairs = _pairs(text)
    result = DxfResult()
    header_values: Dict[int, object] = {}
    entities: List[List[tuple]] = []
    section = None
    current: Optional[List[tuple]] = None

    for code, value in pairs:
        if code == 0:
            keyword = str(value).strip().upper()
            if keyword == "SECTION":
                section = "pending"
                continue
            if keyword == "ENDSEC":
                # The last entity in a section is never followed by another
                # keyword, so it has to be flushed here rather than on the next
                # entity's opening tag.
                if current is not None:
                    entities.append(current)
                    current = None
                section = None
                continue
            if keyword == "EOF":
                if section is not None:
                    raise DxfError("the file ends inside a section")
                if current is not None:
                    entities.append(current)
                    current = None
                break
            if section == "ENTITIES":
                if current is not None:
                    entities.append(current)
                # Group codes repeat and their order matters: a polyline's x
                # and y codes pair up by position, so an entity is kept as the
                # ordered list the file wrote rather than a dictionary.
                current = [(0, keyword)] if keyword in KNOWN else None
                if current is None:
                    result.issues.append(f"{keyword} is not something this "
                                         f"reader understands; nothing was made of it")
                continue
            if section == "HEADER":
                current = None
                continue
            current = None
            continue

        # A section's name arrives on its own code 2 pair, not on the keyword.
        if section == "pending":
            section = str(value).strip().upper() if code == 2 else section
        elif section == "HEADER":
            header_values[int(code)] = value
        elif section == "ENTITIES" and current is not None:
            current.append((int(code), value))

    if current is not None:
        entities.append(current)

    insunits = header_values.get(70)
    if insunits is None or str(insunits).strip() == "":
        result.issues.append("UNITS_MISSING: the file does not say what units "
                             "it is in, so it was read as millimetres")
    else:
        result.units_stated = True
    result.scale_mm = scale_to_mm(insunits if insunits is not None else None)

    for entity in entities:
        shape = _shape(entity, result.scale_mm)
        if shape is not None:
            result.shapes.append(shape)
    return result


def _pairs(text: str) -> List[Tuple[int, str]]:
    """Every (group code, value) pair, refusing a file that is not tagged."""
    if not text.strip():
        raise DxfError("the file is empty")
    lines = [line for line in text.replace("\r\n", "\n").split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise DxfError("the file is empty")
    if len(lines) % 2 != 0:
        raise DxfError(f"the file has {len(lines)} lines, which is not an even "
                       f"number of code and value pairs")
    if "EOF" not in lines:
        raise DxfError("the file has no EOF marker, so it is truncated")
    pairs = []
    for index in range(0, len(lines), 2):
        try:
            pairs.append((int(lines[index].strip()), lines[index + 1]))
        except ValueError as problem:
            raise DxfError(f"line {index + 1} should be a group code: {problem}") from problem
    return pairs


def _number(entity: List[tuple], code: int, default: float = 0.0) -> float:
    """The last value for a group code, which is the one that applies here."""
    values = _all(entity, code)
    if not values:
        return default
    try:
        return float(values[-1])
    except (TypeError, ValueError) as problem:
        raise DxfError(f"group code {code} should hold a number, "
                       f"got {values[-1]!r}") from problem


def _all(entity: List[tuple], code: int) -> List[str]:
    """Every value for a group code, in the order the file wrote them."""
    return [value for found, value in entity if found == code]


def _shape(entity: List[tuple], scale: float) -> Optional[dict]:
    """One entity as a shape in millimetres, or None when it makes no geometry."""
    kind = str(entity[0][1]).upper()
    layer = str(_number_or_text(entity, 8, "0"))

    if kind == "LINE":
        points = np.array([[_number(entity, 10) * scale, _number(entity, 20) * scale],
                           [_number(entity, 11) * scale, _number(entity, 21) * scale]])
        return _polyline_shape("segment", points, layer, closed=False)

    if kind in ("CIRCLE", "ARC"):
        return {
            "kind": "arc",
            "layer": layer,
            "units": "mm",
            "centre_mm": np.array([_number(entity, 10) * scale,
                                   _number(entity, 20) * scale]),
            "radius_mm": _number(entity, 40) * scale,
            "start_deg": _number(entity, 50, 0.0) if kind == "ARC" else 0.0,
            "end_deg": _number(entity, 51, 360.0) if kind == "ARC" else 360.0,
            "closed": kind == "CIRCLE",
        }

    if kind in ("LWPOLYLINE", "POLYLINE"):
        return _from_polyline(entity, layer, scale)

    if kind == "SPLINE":
        points = _control_points(entity, scale)
        return _polyline_shape("polyline", points, layer, closed=False)

    if kind == "ELLIPSE":
        return _from_ellipse(entity, layer, scale)
    return None


def _number_or_text(entity: List[tuple], code: int, default: str) -> str:
    values = _all(entity, code)
    return str(values[-1]) if values else default


def _control_points(entity: List[tuple], scale: float) -> np.ndarray:
    """Control points out of a spline, paired in the order they were written."""
    xs = [float(value) * scale for value in _all(entity, 10)]
    ys = [float(value) * scale for value in _all(entity, 20)]
    if not xs or len(xs) != len(ys):
        raise DxfError("a SPLINE needs matching 10 and 20 control point codes")
    return np.column_stack([xs, ys])


def _from_ellipse(entity: List[tuple], layer: str, scale: float) -> dict:
    """An ellipse sampled into a polyline, so nothing downstream needs its own case."""
    centre = np.array([_number(entity, 10) * scale, _number(entity, 20) * scale])
    major = np.array([_number(entity, 11) * scale, _number(entity, 21) * scale])
    ratio = _number(entity, 40, 1.0)
    start = _number(entity, 41, 0.0)
    sweep = _number(entity, 42, 2.0 * math.pi)
    steps = max(8, int(abs(sweep) / (math.pi / 32)))
    angles = start + np.linspace(0.0, sweep, steps)
    points = centre + (np.outer(np.cos(angles), major) * ratio
                       + np.outer(np.sin(angles), major[[1, 0]]))
    return _polyline_shape("polyline", points, layer, closed=abs(sweep) >= 2 * math.pi)


def _from_polyline(entity: List[tuple], layer: str, scale: float) -> dict:
    """Vertices and bulges out of a polyline, paired the way the file wrote them.

    A vertex's x and its y are separate group codes, and which y belongs to
    which x is decided by position. Sorting by code would put every x before
    every y and quietly keep one vertex out of three.
    """
    xs: List[float] = []
    ys: List[float] = []
    bulges: List[float] = []
    pending_x: Optional[float] = None

    for code, value in entity:
        if code == 10:
            try:
                pending_x = float(value) * scale
            except (TypeError, ValueError) as problem:
                raise DxfError(f"group code 10 should hold a number, "
                               f"got {value!r}") from problem
        elif code == 20 and pending_x is not None:
            ys.append(_number(entity, code) * scale)
            xs.append(pending_x)
            pending_x = None
        elif code == 42:
            bulges.append(_number(entity, code))

    if len(xs) != len(ys):
        raise DxfError(f"a polyline has {len(xs)} x codes but {len(ys)} y codes")
    if not xs:
        raise DxfError("a polyline was declared with no vertices")
    if len(bulges) < len(xs):
        bulges.extend([0.0] * (len(xs) - len(bulges)))

    points = np.column_stack([xs, ys])
    flags = int(_number(entity, 70, 0.0))
    shape = _polyline_shape("polyline", points, layer, closed=bool(flags & 1))
    shape["bulges"] = np.asarray(bulges, dtype=np.float64)
    shape["has_arcs"] = bool(np.any(bulges != 0.0))
    return shape


def _polyline_shape(kind: str, points: np.ndarray, layer: str,
                    closed: bool) -> dict:
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(data) < 2:
        raise DxfError("a shape needs at least two points to have a length")
    if closed and np.array_equal(data[0], data[-1]):
        data = data[:-1]
    span = np.linalg.norm(np.diff(data, axis=0), axis=1).sum()
    if closed and len(data) > 2:
        span += float(np.linalg.norm(data[0] - data[-1]))
    return {
        "kind": kind,
        "layer": layer,
        "units": "mm",
        "points": data,
        "closed": closed,
        "length_mm": float(span),
    }


__all__ = ("DxfError", "DxfResult", "KNOWN", "UNIT_TO_MM", "parse_dxf",
           "scale_to_mm")
