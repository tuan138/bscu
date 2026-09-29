"""
Tab 1 panel: Phôi & Chia mảng (UX-0 shell).

Shows the real selected stock and its state only. Seam tools arrive with UX-6;
this panel must not fake them.
"""
import bpy


def _stock_object(context):
    obj = context.active_object
    return obj


def _dimensions_mm(obj) -> tuple:
    """World-space size in mm, per the scene unit scale (UIUX mục 2.1)."""
    if obj is None:
        return None
    scale = obj.matrix_world.to_scale()
    dims = tuple(d * s for d, s in zip(obj.dimensions, scale))
    return tuple(d * 1000.0 for d in dims)


def _stock_rows(layout, context):
    obj = _stock_object(context)

    if obj is None:
        layout.label(text="Chưa chọn phôi", icon="INFO")
        layout.label(text="Chọn một vật thể Mesh rồi bấm Dùng làm phôi")
        return

    box = layout.box()
    box.label(text=obj.name, icon="MESH_DATA" if obj.type == "MESH" else "MESH_DATA")
    box.label(text=f"Loại: {obj.type}")

    if obj.type != "MESH":
        box.label(text="Chỉ Mesh mới dùng được làm phôi", icon="ERROR")
        return

    dims = _dimensions_mm(obj)
    box.label(text=f"Kích thước: {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm")
    box.label(text=f"Số đỉnh: {len(obj.data.vertices)}")
    box.label(text=f"Số mặt: {len(obj.data.polygons)}")

    uv = obj.data.uv_layers.get("BSCU_UV_Active")
    if uv is None:
        box.label(text="Chưa có bản trải BSCU", icon="RADIOBUT_OFF")
    else:
        box.label(text=f"Bản trải: {uv.name}", icon="CHECKMARK")


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
        _stock_rows(layout, context)

        layout.separator()
        box = layout.box()
        box.label(text="Chia mảng", icon="MOD_MESHDEFORM")
        box.label(text="Công cụ seam sẽ có ở UX-6", icon="INFO")


CLASSES = (BSCU_PT_stock,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
