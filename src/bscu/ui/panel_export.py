"""
The check-and-export panel (UX-11, UIUX 9.3).

Its own file because the project keeps one panel per file, and because drawing
a panel is a different job from exporting: the operator does the work, this
reports it.

The report is cached rather than recomputed on every redraw. A redraw happens
every time the mouse moves over the area, and the checks triangulate the mesh
and walk every edge - on a 200k-face part that is long enough to make the
interface feel broken. The cache is keyed on what the checks actually depend
on, so an edit invalidates it and moving the mouse does not.
"""

import os
from typing import Optional

import bpy

from ..bridge import export_mesh
from ..core.export_check import ExportReport

#: Where the panel puts files when the user has not chosen a folder.
DEFAULT_FOLDER = "//bscu_exports"

#: The last report per object, so a redraw does not redo the checks.
_REPORTS: dict = {}


def _target(context):
    """The object the panel is about, or None."""
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    return obj


def report_for(context, refresh: bool = False) -> Optional[ExportReport]:
    """The pre-export report for the active object, cached until it is asked for."""
    obj = _target(context)
    if obj is None:
        return None
    cached = _REPORTS.get(obj.name)
    if cached is not None and not refresh:
        return cached
    report = export_mesh.check(obj)
    _REPORTS[obj.name] = report
    return report


def forget(obj_name: str) -> None:
    """Drop a cached report, when the object is gone or its mesh changed."""
    _REPORTS.pop(obj_name, None)


def target_path(context) -> str:
    """Where an export would go, resolved against the blend file."""
    obj = _target(context)
    if obj is None:
        return ""
    folder = DEFAULT_FOLDER
    ui = getattr(context.window_manager, "bscu_ui", None)
    if ui is not None and getattr(ui, "export_folder", ""):
        folder = bpy.path.abspath(ui.export_folder)
    return os.path.join(folder, f"{obj.name}.stl")


def draw_panel(layout, context) -> None:
    """Draw the checks and the button, with the button live only when clean."""
    if _target(context) is None:
        layout.label(text="Select a mesh to export", icon="INFO")
        return

    column = layout.column(align=True)
    column.operator("bscu.export_stl", text="Re-check",
                    icon="FILE_REFRESH").refresh = True

    findings = report_for(context)
    if findings is None:
        column.label(text="Nothing to check yet")
        return

    for item in findings.checks:
        column.label(text=item.message,
                     icon="CHECKMARK" if item.ok else "ERROR")
    if findings.max_error_mm:
        column.label(text=f"Largest error {findings.max_error_mm:.4f} mm")

    row = layout.row()
    row.enabled = findings.passed
    row.operator("bscu.export_stl", text="Export STL", icon="EXPORT")
    layout.label(text=target_path(context), icon="FILE_FOLDER")


CLASSES = ()


def register():
    """Nothing to register: the panel is drawn by the canvas inspector."""


def unregister():
    _REPORTS.clear()
