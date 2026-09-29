"""
Writing the relief out as a watertight STL (UX-11, UIUX 9.2 and 9.3).

The export is the last chance to catch a mistake, and the two promises made
here are the ones a machine would hold us to:

* **Watertight, or not exported.** A solid with a hole in it is not a part, and
  a file that writes anyway leaves the user to find out at the machine.
* **Right size, within 0.05 mm.** Checked against the *evaluated* surface rather
  than the design's control points, because a cage can measure right while the
  relief comes out the wrong size.

Units are the other trap. Blender works in metres and a cutter wants
millimetres, so the conversion happens in exactly one place, here, and the
number written is the number that gets checked.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import bpy
import numpy as np

from ..core.export_check import TOLERANCE_MM, ExportReport, build_report

MM_PER_METRE = 1000.0


@dataclass
class ExportResult:
    """What an export attempt did."""

    written: bool
    path: str = ""
    triangles: int = 0
    report: Optional[ExportReport] = None
    reason: str = ""
    blocked: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.written


def millimetre_extents(verts) -> np.ndarray:
    """A mesh's size in millimetres, as (length, width, height)."""
    points = np.asarray(verts, dtype=np.float64).reshape(-1, 3) * MM_PER_METRE
    if not points.size:
        return np.zeros(3, dtype=np.float64)
    return points.max(axis=0) - points.min(axis=0)


def triangle_faces(mesh) -> np.ndarray:
    """A mesh's triangles, so the export check sees what the STL will contain."""
    mesh.calc_loop_triangles()
    return np.asarray([tuple(t.vertices) for t in mesh.loop_triangles],
                      dtype=np.int64)


def check(obj, expected_mm: Optional[Sequence[float]] = None,
          remaining_mm: Optional[np.ndarray] = None,
          tolerance_mm: float = TOLERANCE_MM) -> ExportReport:
    """Run every pre-export check against the object's current state."""
    mesh = obj.data
    verts = np.empty((len(mesh.vertices), 3), dtype=np.float64)
    mesh.vertices.foreach_get("co", verts.ravel())
    faces = triangle_faces(mesh)
    measured = millimetre_extents(verts)
    wanted = np.asarray(expected_mm, dtype=np.float64) if expected_mm is not None \
        else measured
    return build_report(verts, faces, measured, wanted, remaining_mm,
                        tolerance_mm=tolerance_mm)


def export_stl(obj, path: str, report: Optional[ExportReport] = None,
               expected_mm: Optional[Sequence[float]] = None) -> ExportResult:
    """Write a watertight STL in millimetres, if the checks allow it.

    The file is written here rather than handed to Blender's exporter, because
    that exporter writes centimetres and STL carries no unit field to say so.
    The spec allows 0.05 mm, and "multiply by ten because this Blender version
    does that" is not a basis for that tolerance. Writing the bytes ourselves
    puts the unit conversion in one place, in this function, where it is read.
    """
    findings = report if report is not None else check(obj, expected_mm)
    if not findings.passed:
        names = ", ".join(sorted({item.code for item in findings.failures}))
        return ExportResult(False, reason=f"not exported: {names}",
                            blocked=[item.message for item in findings.failures],
                            report=findings)

    mesh = obj.data
    verts = np.empty((len(mesh.vertices), 3), dtype=np.float64)
    mesh.vertices.foreach_get("co", verts.ravel())
    faces = triangle_faces(mesh)
    if faces.size == 0:
        return ExportResult(False, reason="not exported: the mesh has no faces",
                            report=findings)

    # The object's own transform is applied, so where it sits and how big it is
    # on screen cannot decide what a cutter receives. The depsgraph is refreshed
    # first: matrix_world is lazy, so a scale set this frame would otherwise be
    # read as the value from last frame and the part would come out the wrong
    # size without any error anywhere.
    bpy.context.view_layer.update()
    world = np.asarray(obj.matrix_world, dtype=np.float64)
    placed = verts @ world[:3, :3].T + world[:3, 3]

    target = os.path.abspath(os.path.expanduser(path))
    if not target.lower().endswith(".stl"):
        target += ".stl"
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    _write_binary_stl(target, placed, faces)
    return ExportResult(True, path=target, triangles=int(faces.shape[0]),
                        report=findings)


def _write_binary_stl(path: str, verts_mm: np.ndarray, faces: np.ndarray) -> None:
    """Write a binary STL whose numbers are millimetres.

    The mesh arrives in metres from Blender and is converted exactly once, here.
    """
    corners = np.asarray(verts_mm, dtype=np.float64) * MM_PER_METRE
    triangles = corners[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    lengths[lengths == 0.0] = 1.0
    normals = normals / lengths[:, None]

    header = b"BSCU relief export, millimetres".ljust(80, b"\x00")[:80]
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(len(triangles).to_bytes(4, "little"))
        for index in range(len(triangles)):
            row = np.concatenate([normals[index], triangles[index].reshape(-1)])
            handle.write(row.astype("<f4").tobytes())
            handle.write(b"\x00\x00")


__all__ = ("ExportResult", "MM_PER_METRE", "check", "export_stl",
           "millimetre_extents", "triangle_faces")
