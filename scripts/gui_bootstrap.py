"""
Bootstrap for the live Blender GUI used to verify BSCU.

Never calls read_factory_settings(): loading factory settings unregisters
add-ons, which kills the MCP socket server and makes the GUI unreachable.

Run with:
    blender/blender.exe --python scripts/gui_bootstrap.py
"""

import os

import addon_utils
import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_ZIP = os.path.join(REPO_ROOT, "dist", "bscu-1.0.0.zip")

# Blender installs a zip with a blender_manifest.toml as a legacy add-on named
# after the archive root; an extension repo install uses bl_ext.<repo>.<id>.
CANDIDATE_MODULES = ("bscu", "bl_ext.user_default.bscu")


def _log(message: str) -> None:
    print(f"[BSCU Bootstrap] {message}", flush=True)


def setup_units() -> None:
    """Millimetre scene units, per UIUX mục 2.1."""
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "MILLIMETERS"
    scene.unit_settings.scale_length = 0.001
    _log("Scene units set to millimetres")


def _enabled_modules() -> set:
    return {m.module for m in bpy.context.preferences.addons}


def install_bscu() -> str:
    """Install and enable BSCU; return the module name that actually loaded."""
    for module in CANDIDATE_MODULES:
        if module in _enabled_modules():
            _log(f"BSCU already enabled as {module}")
            return module

    if not os.path.exists(DIST_ZIP):
        _log(f"ERROR: extension archive missing at {DIST_ZIP}")
        return ""

    bpy.ops.preferences.addon_install(filepath=DIST_ZIP, overwrite=True)

    for module in CANDIDATE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError as error:
            _log(f"  {module} not available: {error}")
            continue
        if module in _enabled_modules():
            _log(f"BSCU enabled as {module}")
            return module

    _log("ERROR: BSCU could not be enabled")
    return ""


def start_mcp_server() -> None:
    """Start the socket server the AI agent drives the GUI through."""
    if not addon_utils.check("blender_mcp_addon")[1]:
        addon_utils.enable("blender_mcp_addon")
    _log(f"MCP server start result: {bpy.ops.mcp.start_server()}")


def verify_panels(module: str) -> None:
    """Report which BSCU panels Blender actually registered."""
    panels = sorted(
        name
        for name in dir(bpy.types)
        if name.startswith("BSCU_PT_")
    )
    _log(f"Registered BSCU panels: {panels}")
    if not panels:
        _log(f"ERROR: no panels registered for {module}")


if __name__ == "__main__":
    setup_units()
    active_module = install_bscu()
    start_mcp_server()
    verify_panels(active_module)
    _log("BLENDER_GUI_READY on 127.0.0.1:9876")
