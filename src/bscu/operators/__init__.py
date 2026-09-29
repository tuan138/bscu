"""
Operators package for BSCU.
"""

from . import op_draw, op_export, op_reload, op_seam, op_uv_apply

MODULES = (op_reload, op_seam, op_uv_apply, op_export, op_draw)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
