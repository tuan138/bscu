"""
Operator for hot-reloading BSCU Add-on modules in live Blender session.
"""

import bpy

from ..core.reloader import reload_bscu_modules
from ..registry import register_classes, unregister_classes


class BSCU_OT_Reload(bpy.types.Operator):
    """Hot-reload all BSCU modules without restarting Blender"""

    bl_idname = "bscu.reload"
    bl_label = "Reload BSCU Add-on"
    bl_description = "Reload all python modules of BSCU addon in place"

    def execute(self, context):
        reloaded = reload_bscu_modules()
        msg = f"Reloaded {len(reloaded)} BSCU modules"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


CLASSES = (BSCU_OT_Reload,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
