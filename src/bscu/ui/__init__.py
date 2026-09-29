"""
UI package for BSCU. Each panel module registers itself; nothing is listed here.
"""

from . import panel_downstream, panel_inspector, panel_steps, panel_stock

MODULES = (panel_steps, panel_stock, panel_downstream, panel_inspector)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
