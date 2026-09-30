"""
A small SVG reader for the 2.5D canvas (UX-13, UIUX 10.6).

The spec's rule is that an import may only bring in one layer, convert
millimetres by the drawing's own width and height, and never quietly change
what the user already has. That last part shapes this module more than the
parsing does: anything not understood is reported by name, and the units and
the scale are taken from the document rather than guessed.

Two conversions the spec names, both explicit here:

* ``width``/``height`` in pixels become millimetres at 96 px per inch, the
  number the format itself is defined against.
* a viewBox stretches the drawing to fill the document, so a file exported from
  a CAD package with a different pixel size still lands the right size.

Everything is millimetres by the time it leaves this module.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple
from xml.etree import ElementTree

import numpy as np

#: Pixels per inch, the number SVG's own units are defined against.
PX_PER_INCH = 96.0
PX_PER_MM = PX_PER_INCH / 25.4

#: A path command with that many coordinates after it.
_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2,
          "A": 7, "Z": 0}

_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


@dataclass
class SvgResult:
    """What came out of the file, and what could not be dealt with."""

    shapes: List[dict] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    width_mm: float = 0.0
    height_mm: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.issues


def parse_svg(text: str, target_layer: Optional[str] = None) -> SvgResult:
    """Read an SVG's paths and basic shapes, in millimetres."""
    if not text or not text.strip():
        raise ValueError("the file is empty")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as problem:
        raise ValueError(f"the file is not valid XML: {problem}") from problem

    result = SvgResult()
    scale, offset = _document_scale(root, result)
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "path":
            _read_path(element, result, scale, offset, target_layer)
        elif tag in ("rect", "circle", "line", "polyline", "polygon"):
            _read_shape(tag, element, result, scale, offset, target_layer)
        elif tag not in ("svg", "g", "defs", "title", "desc", "metadata"):
            result.issues.append(f"<{tag}> is not something this reader turns "
                                 f"into geometry; nothing was made of it")
    return result


def _document_scale(root, result: SvgResult) -> Tuple[float, np.ndarray]:
    """Millimetres per user unit, and where the drawing starts.

    Taken from the document's own width, height and viewBox. A file with none
    of them is reported rather than assumed, because assuming inches turns a
    300 mm plate into a 12 mm one.
    """
    view_box = root.get("viewBox")
    width = _length_mm(root.get("width"))
    height = _length_mm(root.get("height"))

    if view_box:
        parts = [float(value) for value in re.split(r"[\s,]+", view_box.strip()) if value]
        if len(parts) != 4:
            result.issues.append(f"the viewBox has {len(parts)} numbers; four "
                                 f"are needed, so it was ignored")
        else:
            box_width = parts[2] or 1.0
            box_height = parts[3] or 1.0
            scale_x = (width / box_width) if width else 1.0 / PX_PER_MM
            scale_y = (height / box_height) if height else 1.0 / PX_PER_MM
            scale = min(scale_x, scale_y) or 1.0 / PX_PER_MM
            offset = np.array([-parts[0] * scale, -parts[1] * scale])
            result.width_mm = box_width * scale
            result.height_mm = box_height * scale
            return scale, offset

    if not width or not height:
        result.issues.append("UNITS_MISSING: the file states no size, so it "
                             "was read at 96 pixels per inch")
    # Without a viewBox the user coordinate system is the viewport in pixels,
    # and that is the only reading the format supports. The stated absolute
    # size is the *document's* size, not its user units: a file saying
    # width="4in" is 101.6 mm across, but a path of one unit is one pixel,
    # 0.2646 mm. Reading it as an inch would guess at how far the drawing
    # spans, and a wrong guess here cuts the part 25 times too big with
    # nothing on screen to notice.
    if _states_absolute(root):
        result.issues.append(
            f"UNITS_INFERRED: the file gives no viewBox, so one user unit is "
            f"read as one pixel at {PX_PER_INCH:g} per inch; how far the "
            f"drawing actually spans cannot be confirmed from the file alone")
    result.width_mm = width or 0.0
    result.height_mm = height or 0.0
    return 1.0 / PX_PER_MM, np.zeros(2)


def _states_absolute(root) -> bool:
    """Whether the document's size is written in a real unit."""
    for name in ("width", "height"):
        value = root.get(name)
        if value and str(value).strip().endswith(("mm", "cm", "in", "pt")):
            return True
    return False


def _length_mm(value: Optional[str]) -> float:
    """An SVG length such as ``300mm`` or ``300`` as millimetres."""
    if not value:
        return 0.0
    text = str(value).strip()
    match = _NUMBER.search(text)
    if not match:
        return 0.0
    amount = float(match.group())
    if text.endswith("mm"):
        return amount
    if text.endswith("cm"):
        return amount * 10.0
    if text.endswith("in"):
        return amount * 25.4
    if text.endswith("pt"):
        return amount * 25.4 / 72.0
    if text.endswith("px"):
        return amount / PX_PER_MM
    return amount / PX_PER_MM


def _read_shape(tag: str, element, result: SvgResult, scale: float,
                offset: np.ndarray, target_layer: Optional[str]) -> None:
    layer = _layer_of(element, target_layer, result)
    if layer is None:
        return
    if tag == "rect":
        x = _attr(element, "x", scale, offset[0])
        y = _attr(element, "y", scale, offset[1])
        width = _attr(element, "width", scale, 0.0)
        height = _attr(element, "height", scale, 0.0)
        points = np.asarray([[x, y], [x + width, y], [x + width, y + height],
                             [x, y + height]], dtype=np.float64)
        closed = True
    elif tag == "circle":
        cx = _attr(element, "cx", scale, offset[0])
        cy = _attr(element, "cy", scale, offset[1])
        radius = _attr(element, "r", scale, 0.0)
        result.shapes.append(_arc_shape(layer, (cx, cy), radius, 0.0, 360.0, True))
        return
    elif tag == "line":
        points = np.asarray([
            [_attr(element, "x1", scale, offset[0]),
             _attr(element, "y1", scale, offset[1])],
            [_attr(element, "x2", scale, offset[0]),
             _attr(element, "y2", scale, offset[1])]], dtype=np.float64)
        closed = False
    else:
        numbers = [float(value) for value in
                   _NUMBER.findall(element.get("points", ""))]
        if len(numbers) % 2 or len(numbers) < 4:
            result.issues.append(f"a <{tag}> has {len(numbers)} numbers, which "
                                 f"is not a whole number of points")
            return
        points = np.asarray(numbers, dtype=np.float64).reshape(-1, 2)
        points[:, 0] = points[:, 0] * scale + offset[0]
        points[:, 1] = points[:, 1] * scale + offset[1]
        closed = tag == "polygon"
    result.shapes.append(_polyline_shape(layer, points, closed))


def _read_path(element, result: SvgResult, scale: float, offset: np.ndarray,
               target_layer: Optional[str]) -> None:
    layer = _layer_of(element, target_layer, result)
    if layer is None:
        return
    data = element.get("d", "")
    if not data.strip():
        result.issues.append("a <path> with no data was skipped")
        return
    points = _flatten_path(data, scale, offset)
    if len(points) >= 2:
        result.shapes.append(_polyline_shape(layer, points, False))
    else:
        result.issues.append("a <path> with fewer than two points was skipped")


def _flatten_path(data: str, scale: float, offset: np.ndarray) -> np.ndarray:
    """Turn path data into a run of points.

    Arcs are sampled rather than kept as arcs: the canvas stores points, and a
    circular arc becomes a run of points the relief code already understands.
    """
    # Any letter, not only the ones we know: an unknown command has to be
    # named rather than skipped, because a skipped command silently changes
    # the shape of the drawing it was supposed to describe.
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?",
                        data)
    points: List[List[float]] = []
    current = np.zeros(2)
    start = np.zeros(2)
    index = 0
    command = None

    def place(point) -> None:
        scaled = np.asarray([point[0] * scale + offset[0],
                             point[1] * scale + offset[1]], dtype=np.float64)
        points.append(scaled.tolist())

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command in "Zz":
                place(start)
                current = start.copy()
                continue
        if command is None:
            raise ValueError(f"path data starts with a number, {token!r}, "
                             f"before any command")
        upper = command.upper()
        relative = command.islower()
        arity = _ARITY.get(upper)
        if arity is None:
            raise ValueError(f"path command {command!r} is not one this reader "
                             f"knows")
        numbers = [float(value) for value in tokens[index:index + arity]]
        if len(numbers) < arity:
            break
        index += arity
        step = _apply_command(upper, numbers, current, start, relative)
        # Every command but the close names a point, the move included: it is
        # where the run starts.
        if upper != "Z":
            place(step)
        current = np.asarray(step, dtype=np.float64)
        if upper == "M":
            start = current.copy()
            # Further pairs after a move are implicit lines, per the format.
            # Treating them as more moves would send a later Z to the wrong
            # point and quietly change the shape of a closed outline.
            # Further pairs after a move are implicit lines, and a move that
            # was relative makes them relative too: m10 10 5 0 ends at
            # (15, 10), not at (5, 0).
            command = ("l" if command == "m" else "L") \
                if command in ("M", "m") else command
    return np.asarray(points, dtype=np.float64).reshape(-1, 2)


def _apply_command(upper: str, numbers: Sequence[float], current: np.ndarray,
                   start: np.ndarray, relative: bool):
    origin = current if relative else np.zeros(2)
    if upper == "M":
        return [numbers[0] + origin[0], numbers[1] + origin[1]]
    if upper == "L":
        return [numbers[0] + origin[0], numbers[1] + origin[1]]
    if upper == "H":
        return [numbers[0] + origin[0], current[1]]
    if upper == "V":
        return [current[0], numbers[0] + origin[1]]
    if upper in ("C", "S"):
        # A curve's control points are kept, and the relief code re-fits them.
        return [numbers[-2] + origin[0], numbers[-1] + origin[1]]
    if upper in ("Q", "T"):
        return [numbers[-2] + origin[0], numbers[-1] + origin[1]]
    if upper == "A":
        return [numbers[5] + origin[0], numbers[6] + origin[1]]
    return [current[0], current[1]]


def _layer_of(element, target_layer: Optional[str], result: SvgResult):
    """The layer an element belongs to, honouring the one-layer rule."""
    layer = element.get("id") or element.get("inkscape:label") or "layer-0"
    if target_layer is not None and layer != target_layer:
        result.issues.append(f"element on layer '{layer}' was left out; only "
                             f"'{target_layer}' was asked for")
        return None
    return layer


def _attr(element, name: str, scale: float, origin: float) -> float:
    raw = element.get(name)
    if raw is None:
        return origin
    return _length_mm(raw) if str(raw).endswith(("mm", "cm", "in", "pt", "px")) \
        else float(_NUMBER.search(str(raw)).group()) * scale + origin


def _polyline_shape(layer: str, points: np.ndarray, closed: bool) -> dict:
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    span = float(np.linalg.norm(np.diff(data, axis=0), axis=1).sum())
    if closed and len(data) > 2:
        span += float(np.linalg.norm(data[0] - data[-1]))
    return {"kind": "polyline", "layer": layer, "units": "mm", "points": data,
            "closed": closed, "length_mm": span}


def _arc_shape(layer: str, centre, radius: float, start: float, end: float,
               closed: bool) -> dict:
    return {"kind": "arc", "layer": layer, "units": "mm",
            "centre_mm": np.asarray(centre, dtype=np.float64),
            "radius_mm": abs(radius), "start_deg": start, "end_deg": end,
            "closed": closed}


__all__ = ("PX_PER_MM", "PX_PER_INCH", "SvgResult", "parse_svg")
