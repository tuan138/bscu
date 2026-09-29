"""
Properties package for BSCU. One PropertyGroup per module, each self-registering.
"""

from . import design_props, ui_props

MODULES = (ui_props, design_props)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
