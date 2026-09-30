"""
Exporting the relief as an STL (UX-11, UIUX 9.2 and 9.3).

The panel is in :mod:`bscu.ui.panel_export`; this is the action it offers. The
gate is the point of the pair: a candidate only reaches ``BSCU_UV_Active``-style
output after the checks are clean, and a file that would be bad is never
written at all.

Exporting goes through an operator, so Blender's Undo covers it and a refused
export leaves nothing behind on the document.
"""

import bpy

from ..bridge import export_mesh
from ..registry import register_classes, unregister_classes


class BSCU_OT_ExportSTL(bpy.types.Operator):
    """Write the relief out as a watertight STL, if the checks allow it"""

    bl_idname = "bscu.export_stl"
    bl_label = "Export STL"
    # Deliberately not UNDO: an export writes a file outside the document, so
    # offering an undo step would put the file and the undo stack out of step
    # with each other.
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(name="File Path", subtype="FILE_PATH")
    check_only: bpy.props.BoolProperty(
        name="Check only",
        default=False,
        description="Run the checks and report, without writing anything")
    refresh: bpy.props.BoolProperty(
        name="Re-check",
        default=False,
        description="Run the checks again instead of using the cached report")

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select the mesh to export first")
            return {"CANCELLED"}

        from ..ui import panel_export

        destination = self.filepath or panel_export.target_path(context)

        if self.check_only:
            findings = panel_export.report_for(context, refresh=True)
            for item in findings.checks:
                self.report({"INFO" if item.ok else "ERROR"}, item.message)
            if findings.passed:
                return {"FINISHED"}
            self.report({"WARNING"}, "the checks found something to fix")
            return {"CANCELLED"}

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
        # A check never needs a file browser: the panel's Check button would
        # otherwise open a dialog for an operation that writes nothing.
        if self.check_only or self.refresh:
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


CLASSES = (BSCU_OT_ExportSTL,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
