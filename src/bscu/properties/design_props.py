"""
Blender-side design properties (UX-2, UIUX K2).

A PropertyGroup so the design tree has a real home in the .blend file and is
carried by Blender's own Undo, rather than living in a Python dict that Undo
would silently throw away.
"""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from ..bridge.design_store import DesignStore, ensure_design

ELEMENT_KIND_ITEMS = [
    ("STROKE", "Nét", "Đường vẽ tự do"),
    ("REGION", "Mảng", "Vùng khép kín nâng cao"),
    ("GRID", "Lưới nắn", "Lưới nắn theo khu vực"),
]

REGION_MODE_ITEMS = [
    ("WHOLE", "Toàn phôi", "Dùng toàn bộ phôi"),
    ("SELECTED", "Vùng chọn", "Chỉ dùng các mặt đang chọn"),
]


class BSCU_PG_element(bpy.types.PropertyGroup):
    """One named design element; the ID is what other data refers to."""

    design_id: IntProperty(name="ID", default=0)
    name: StringProperty(name="Tên", default="")
    kind: EnumProperty(name="Loại", items=ELEMENT_KIND_ITEMS, default="STROKE")
    visible: BoolProperty(name="Hiện", default=True)
    locked: BoolProperty(name="Khoá", default=False)


class BSCU_PG_design(bpy.types.PropertyGroup):
    """The design attached to one stock object."""

    elements: CollectionProperty(type=BSCU_PG_element)
    elements_active: IntProperty(name="Phần tử đang chọn", default=0)
    region_mode: EnumProperty(name="Vùng trang trí", items=REGION_MODE_ITEMS, default="WHOLE")


CLASSES = (BSCU_PG_element, BSCU_PG_design)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.bscu_design = PointerProperty(type=BSCU_PG_design)


def unregister():
    del bpy.types.Object.bscu_design
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


def attach(obj) -> None:
    """Make sure the stock has both the property group and the ID slot."""
    ensure_design(obj)


def store_for(obj) -> DesignStore:
    """The durable design store of a stock object."""
    return DesignStore(obj)
