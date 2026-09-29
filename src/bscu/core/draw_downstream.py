"""
Pure drawing helpers for the gated tabs Caro / Bản trải / Tạo phù điêu (UX-0).
"""

from .workflow import STEP_LABELS, is_step_unlocked

LOCKED_ICON = "LOCKED"
INFO_ICON = "INFO"

# What the user must finish before this tab becomes usable.
TAB_PREREQUISITES = {
    "SEAM": "Chưa có phôi",
    "LAYOUT": "Chưa có bản trải Caro",
    "RELIEF": "Chưa duyệt bản trải",
}

TAB_ROADMAP = {
    "SEAM": "Đề xuất cách chia, 4 công cụ seam và cọ chỉ dẫn (UX-4, UX-5, UX-6)",
    "LAYOUT": "Dàn đều, bản đồ nhiệt méo, cọ chỉ dẫn và duyệt bản trải (UX-5, UX-8)",
    "RELIEF": "Vẽ đường, dáng mảng, lưới nắn và xuất STL (UX-9a, UX-10, UX-11)",
}


def draw_gated_tab(layout, facts, step):
    """Show either the blocker or the roadmap for the tab's own scope."""
    unlocked, blocker = is_step_unlocked(step, facts)

    if not unlocked:
        box = layout.box()
        box.label(text=TAB_PREREQUISITES[step], icon=LOCKED_ICON)
        box.label(text=f"Hoàn thành “{STEP_LABELS[blocker]}” trước")
        return

    layout.label(text="Chưa có gì để hiển thị ở bước này", icon=INFO_ICON)
    box = layout.box()
    box.label(text="Sẽ có ở giai đoạn sau:", icon=INFO_ICON)
    box.label(text=TAB_ROADMAP[step])
