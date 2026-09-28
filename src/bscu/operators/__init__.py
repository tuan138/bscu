"""
Operators package for BSCU.
"""

from . import op_reload


def register():
    op_reload.register()


def unregister():
    op_reload.unregister()
