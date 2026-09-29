"""
Writing a candidate layout to the mesh (UX-8, UIUX 3B.6 and 4.5).

The gate is the point of this module. A candidate only reaches
``BSCU_UV_Active`` after the validator has cleared it, and when a layout is
already there the user has to say what should happen to it. Overwriting silently
is how a day of seam work disappears.

Applying goes through a normal operator so Blender's Undo takes it. Nothing
here writes to the mesh until the decision is made and the checks have passed.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import bpy
import numpy as np

from ..core.uv_validate import ChartReport, validate_chart

#: The one map the rest of the pipeline reads.
ACTIVE_UV = "BSCU_UV_Active"


class Decision(Enum):
    """What to do with the layout that is already applied."""

    KEEP_OLD = "keep_old"
    TAKE_NEW = "take_new"


@dataclass
class ApplyResult:
    """What the gate did, and what stopped it when it stopped."""

    applied: bool
    reason: str = ""
    blocked: List[str] = field(default_factory=list)
    revision: int = 0

    def __bool__(self) -> bool:
        return self.applied


def active_map(mesh) -> Optional[bpy.types.MeshUVLoopLayer]:
    """The map the pipeline owns, or None when there is not one yet."""
    return mesh.uv_layers.get(ACTIVE_UV)


def has_active_map(obj) -> bool:
    return active_map(obj.data) is not None


def read_layout(obj) -> Optional[np.ndarray]:
    """One UV point per mesh vertex from the active map."""
    layer = active_map(obj.data)
    if layer is None:
        return None
    points = np.zeros((len(obj.data.vertices), 2), dtype=np.float64)
    for loop in obj.data.loops:
        uv = layer.data[loop.index].uv
        points[loop.vertex_index] = (uv.x, uv.y)
    return points


def write_layout(obj, layout) -> int:
    """Write a layout into the active map, creating it when needed.

    Returns the number of loops written. The map is only created once the gate
    has already said yes.
    """
    data = np.asarray(layout, dtype=np.float64).reshape(-1, 2)
    layer = active_map(obj.data)
    if layer is None:
        layer = obj.data.uv_layers.new(name=ACTIVE_UV)
    written = 0
    for loop in obj.data.loops:
        if loop.vertex_index < len(data):
            layer.data[loop.index].uv = (float(data[loop.vertex_index, 0]),
                                         float(data[loop.vertex_index, 1]))
            written += 1
    return written


def island_labels(obj) -> Tuple[np.ndarray, np.ndarray]:
    """Triangles of the mesh and the chart each one belongs to."""
    from ..core.uv_islands import extract_islands

    mesh = obj.data
    mesh.calc_loop_triangles()
    faces = np.asarray([tuple(t.vertices) for t in mesh.loop_triangles],
                       dtype=np.int64)
    if not faces.size:
        return faces, np.zeros(0, dtype=np.int64)
    seams = [tuple(sorted(edge.vertices)) for edge in mesh.edges if edge.use_seam]
    return faces, extract_islands(faces, seams)


def check_candidate(obj, layout) -> ChartReport:
    """Validate a candidate layout against the mesh's current seams."""
    faces, islands = island_labels(obj)
    points = np.asarray(layout, dtype=np.float64).reshape(-1, 2)
    return validate_chart(faces, points, islands)


def apply_candidate(obj, layout, decision: Optional[Decision] = None,
                    report: Optional[ChartReport] = None) -> ApplyResult:
    """Write a candidate layout, if it is allowed to be written.

    A candidate with an error is refused outright: a bad layout is worse than
    no layout, because the displacement downstream would be confidently wrong.
    When a layout is already applied, the caller has to choose.
    """
    data = np.asarray(layout, dtype=np.float64).reshape(-1, 2)
    if len(data) < len(obj.data.vertices):
        return ApplyResult(False, "candidate has fewer points than the mesh has vertices")

    findings = report if report is not None else check_candidate(obj, data)
    if findings.errors:
        names = ", ".join(sorted({f.code for f in findings.errors}))
        return ApplyResult(False, f"candidate has errors: {names}",
                           [f.message for f in findings.errors])

    if has_active_map(obj):
        if decision is None:
            return ApplyResult(False, "a layout is already applied; choose "
                                     "keep old or take new")
        if decision is Decision.KEEP_OLD:
            return ApplyResult(True, "kept the layout already applied")

    write_layout(obj, data)
    return ApplyResult(True, "candidate applied")


def active_report(obj) -> ChartReport:
    """Validate whatever layout is currently applied."""
    faces, islands = island_labels(obj)
    layout = read_layout(obj)
    if layout is None:
        return ChartReport()
    return validate_chart(faces, layout, islands)


__all__ = (
    "ACTIVE_UV",
    "ApplyResult",
    "Decision",
    "active_map",
    "active_report",
    "apply_candidate",
    "check_candidate",
    "has_active_map",
    "island_labels",
    "read_layout",
    "write_layout",
)
