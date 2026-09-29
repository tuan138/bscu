"""
Exporting the relief as an STL (UX-11, UIUX 9.2 and 9.3).

The panel is the same shape as the spec's "check and export" section: run every
check, show what failed and where, and only then offer the button. The button
is deliberately inert until the checks are clean, so a user cannot reach a file
that is open or the wrong size by clicking faster than they can read.

Exporting goes through an operator, so Blender's Undo covers it and a refused
export leaves nothing behind on the document.
"""

import os

import bpy

from ..bridge import export_mesh

#: Where the panel puts the file when the user has not chosen.
DEFAULT_FOLDER = "//bscu_exports"


def _target(context) -> str:
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        raise ValueError("select the mesh to export first")
    return obj


def report_for(context):
    """The pre-export report for the active object, for the panel to draw."""
    return export_mesh.check(_target(context))


def target_path(context) -> str:
    """Where an export would go, resolved against the blend file."""
    folder = bpy.path.abspath(getattr(context.scene.bscu_ui, "export_folder",
                                       DEFAULT_FOLDER)
                              if hasattr(context.scene, "bscu_ui")
                              else DEFAULT_FOLDER)
    name = _target(context).name
    return os.path.join(folder, f"{name}.stl")


class BSCU_OT_ExportSTL(bpy.types.Operator):
    """Write the relief out as a watertight STL, if the checks allow it"""

    bl_idname = "bscu.export_stl"
    bl_label = "Export STL"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(name="File Path", subtype="FILE_PATH")
    check_only: bpy.props.BoolProperty(
        name="Check only",
        default=False,
        description="Run the checks and report, without writing anything")

    def execute(self, context):
        obj = _target(context)
        destination = self.filepath or target_path(context)
        if self.check_only:
            findings = export_mesh.check(obj)
            for item in findings.checks:
                self.report({"INFO" if item.ok else "ERROR"}, item.message)
            return {"FINISHED"} if findings.passed else {"CANCELLED"}

        result = export_mesh.export_stl(obj, destination)
        if not result:
            self.report({"ERROR"}, result.reason)
            for line in result.blocked:
                self.report({"WARNING"}, line)
            return {"CANCELLED"}
        self.report({"INFO"},
                    f"wrote {result.triangles} triangles to {result.path}")
        return {"FINISHED"}

    def invoke(self, context, event):
        window_manager = context.window_manager
        window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


def class_callback(context) -> tuple:
    """What the panel shows: the report and where the file would go."""
    try:
        return report_for(context), target_path(context)
    except ValueError:
        return None, ""


def draw_panel(layout, context) -> None:
    """Draw the check-and-export panel."""
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        layout.label(text="Select a mesh to export", icon="INFO")
        return

    findings, destination = class_callback(context)
    if findings is None:
        layout.label(text="Nothing to check yet")
        return

    column = layout.column(align=True)
    for item in findings.checks:
        column.label(text=item.message, icon="CHECKMARK" if item.ok else "ERROR")

    if findings.max_error_mm:
        column.label(text=f"Largest error {findings.max_error_mm:.4f} mm")

    row = layout.row()
    row.enabled = findings.passed
    row.operator("bscu.export_stl", text="Export STL")
    row = layout.row()
    row.operator("bscu.export_stl", text="Check Only").check_only = True
    layout.label(text=destination, icon="FILE_FOLDER")


CLASSES = (BSCU_OT_ExportSTL,)


def register():
    from ..registry import register_classes

    return register_classes(CLASSES)


def unregister():
    from ..registry import unregister_classes

    return unregister_classes(CLASSES)
