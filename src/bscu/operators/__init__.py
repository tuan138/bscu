"""
Operators package for BSCU.
"""

from . import op_reload, op_seam, op_uv_apply

MODULES = (op_reload, op_seam, op_uv_apply)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
