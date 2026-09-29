"""
Tab 1 panel: Phôi & Chia mảng (UX-0 shell).

Shows the real selected stock and its state only. Seam tools arrive with UX-6;
this panel must not fake them.
"""

import bpy

from ..core.draw_stock import draw_no_stock, draw_stock_summary
from ..registry import register_classes, unregister_classes
from .context import active_stock


def stock_dimensions_mm(obj):
    """World-space size in mm, per the scene unit scale (UIUX mục 2.1)."""
    scale = obj.matrix_world.to_scale()
    return tuple(d * s * 1000.0 for d, s in zip(obj.dimensions, scale))


def draw_stock(layout, obj):
    """Render the selected stock, or the prompt to pick one."""
    if obj is None:
        draw_no_stock(layout)
        return

    mesh = obj.data if obj.type == "MESH" else None
    draw_stock_summary(
        layout,
        name=obj.name,
        obj_type=obj.type,
        dims_mm=stock_dimensions_mm(obj),
        vert_count=len(mesh.vertices) if mesh else 0,
        face_count=len(mesh.polygons) if mesh else 0,
        has_uv=mesh is not None and mesh.uv_layers.get("BSCU_UV_Active") is not None,
    )


class BSCU_PT_stock(bpy.types.Panel):
    bl_label = "Phôi & Chia mảng"
    bl_idname = "BSCU_PT_stock"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    @classmethod
    def poll(cls, context):
        return context.window_manager.bscu_ui.active_tab == "STOCK"

    def draw(self, context):
        layout = self.layout
        draw_stock(layout, active_stock(context))

        layout.separator()
        box = layout.box()
        box.label(text="Chia mảng", icon="MOD_MESHDEFORM")
        box.label(text="Công cụ seam sẽ có ở UX-6", icon="INFO")


CLASSES = (BSCU_PT_stock,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
