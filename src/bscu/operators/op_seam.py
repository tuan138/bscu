"""
The four seam tools as operators (UX-6, UIUX 3.2).

Each one stages a candidate and leaves the mesh alone. Confirming is a separate
operator, and cancelling is Esc, so the chain the user previewed is exactly the
chain that lands. Space is left alone on purpose: taking it would fight the
animation play controls.
"""

import bpy

from ..bridge import seam_bridge


def _target(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        raise ValueError("select the mesh to cut before using a seam tool")
    return obj


class BSCU_OT_SeamChain(bpy.types.Operator):
    """Cut a seam along the existing edge chain between two picked points"""

    bl_idname = "bscu.seam_chain"
    bl_label = "Seam Through Points"
    bl_options = {"REGISTER", "UNDO"}

    start_vertex: bpy.props.IntProperty(
        name="Start", default=0, description="Vertex the seam starts at")
    goal_vertex: bpy.props.IntProperty(
        name="Goal", default=1, description="Vertex the seam ends at")

    def execute(self, context):
        obj = _target(context)
        try:
            staged = seam_bridge.propose_chain(obj, self.start_vertex, self.goal_vertex)
        except seam_bridge.ChainError as problem:
            self.report({"ERROR"}, str(problem))
            return {"CANCELLED"}
        self.report({"INFO"}, f"{staged['label']}: {len(staged['edges'])} edge(s)")
        return {"FINISHED"}


class BSCU_OT_SeamSelectionBorder(bpy.types.Operator):
    """Cut a seam along the border of the selected faces"""

    bl_idname = "bscu.seam_selection_border"
    bl_label = "Seam Selection Border"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _target(context)
        selected = [polygon.select for polygon in obj.data.polygons]
        staged = seam_bridge.propose_selection_border(obj, selected)
        self.report({"INFO"}, f"{staged['label']}; press Confirm to apply")
        return {"FINISHED"}


class BSCU_OT_SeamNearPlane(bpy.types.Operator):
    """Suggest a path along the existing edges nearest a reference plane"""

    bl_idname = "bscu.seam_near_plane"
    bl_label = "Seam Near Reference Plane"
    bl_options = {"REGISTER", "UNDO"}

    origin: bpy.props.FloatVectorProperty(
        name="Plane Point", size=3, default=(0.0, 0.0, 0.0),
        description="A point on the reference plane")
    normal: bpy.props.FloatVectorProperty(
        name="Plane Normal", size=3, default=(0.0, 0.0, 1.0),
        description="Which way the reference plane faces")
    tolerance: bpy.props.FloatProperty(
        name="Tolerance", default=0.002, min=1e-5, unit="LENGTH",
        description="How far from the plane an edge may sit and still be offered")

    def execute(self, context):
        obj = _target(context)
        try:
            staged = seam_bridge.propose_near_plane(
                obj, self.origin, self.normal, self.tolerance)
        except ValueError as problem:
            self.report({"ERROR"}, str(problem))
            return {"CANCELLED"}
        note = f"{staged['label']}; this does not cut the mesh"
        self.report({"INFO"}, note)
        return {"FINISHED"}


class BSCU_OT_SeamViewContour(bpy.types.Operator):
    """Suggest seam edges where the face normals meet the line of sight"""

    bl_idname = "bscu.seam_view_contour"
    bl_label = "Seam Along View Contour"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _target(context)
        try:
            direction = seam_bridge.view_direction(context)
        except seam_bridge.ChainError as problem:
            self.report({"ERROR"}, str(problem))
            return {"CANCELLED"}
        staged = seam_bridge.propose_contour(obj, direction)
        self.report({"INFO"}, f"{staged['label']}; occlusion is not checked")
        return {"FINISHED"}


class BSCU_OT_SeamConfirm(bpy.types.Operator):
    """Apply the seam the tools have been previewing"""

    bl_idname = "bscu.seam_confirm"
    bl_label = "Use This Cut"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _target(context)
        candidate = seam_bridge.staged(obj)
        if not candidate["edges"]:
            self.report({"WARNING"}, "no candidate seam to apply")
            return {"CANCELLED"}
        changed = seam_bridge.confirm(obj)
        self.report({"INFO"}, f"{len(candidate['edges'])} edge(s) marked as seam")
        return {"FINISHED"} if changed >= 0 else {"CANCELLED"}


class BSCU_OT_SeamCancel(bpy.types.Operator):
    """Throw away the candidate seam and leave the mesh as it was"""

    bl_idname = "bscu.seam_cancel"
    bl_label = "Cancel Cut"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _target(context)
        seam_bridge.clear_stage(obj.name)
        self.report({"INFO"}, "candidate seam discarded")
        return {"FINISHED"}


CLASSES = (
    BSCU_OT_SeamChain,
    BSCU_OT_SeamSelectionBorder,
    BSCU_OT_SeamNearPlane,
    BSCU_OT_SeamViewContour,
    BSCU_OT_SeamConfirm,
    BSCU_OT_SeamCancel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
