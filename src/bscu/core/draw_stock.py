"""
Pure drawing helpers for the stock panel (UX-0).

Takes already-measured values so no Blender access leaks into the drawing code.
"""

STOCK_MESH_ICON = "MESH_DATA"
STOCK_MISSING_ICON = "INFO"
STOCK_WRONG_TYPE_ICON = "ERROR"
STOCK_NO_UV_ICON = "RADIOBUT_OFF"
STOCK_UV_ICON = "CHECKMARK"

BSCU_UV_NAME = "BSCU_UV_Active"


def draw_no_stock(layout):
    """Explain what to do when nothing is selected."""
    layout.label(text="Chưa chọn phôi", icon=STOCK_MISSING_ICON)
    layout.label(text="Chọn một vật thể Mesh rồi bấm Dùng làm phôi")


def draw_stock_summary(layout, name, obj_type, dims_mm, vert_count, face_count,
                       has_uv, uv_name=BSCU_UV_NAME):
    """Render the measured stock state inside a boxed layout."""
    box = layout.box()
    box.label(text=name, icon=STOCK_MESH_ICON)
    box.label(text=f"Loại: {obj_type}")

    if obj_type != "MESH":
        box.label(text="Chỉ Mesh mới dùng được làm phôi", icon=STOCK_WRONG_TYPE_ICON)
        return

    width, depth, height = dims_mm
    box.label(text=f"Kích thước: {width:.1f} × {depth:.1f} × {height:.1f} mm")
    box.label(text=f"Số đỉnh: {vert_count}")
    box.label(text=f"Số mặt: {face_count}")

    if has_uv:
        box.label(text=f"Bản trải: {uv_name}", icon=STOCK_UV_ICON)
    else:
        box.label(text="Chưa có bản trải BSCU", icon=STOCK_NO_UV_ICON)
