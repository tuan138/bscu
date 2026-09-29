"""
Operators package for BSCU.
"""

from . import op_reload, op_seam

MODULES = (op_reload, op_seam)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
