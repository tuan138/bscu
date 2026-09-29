"""
Startup script for Blender GUI mode.
Enables blender_mcp_addon and starts the socket server so AI Agent can control the live GUI.
"""

import addon_utils
import bpy


def setup():
    print("[Blender GUI] Enabling blender_mcp_addon...", flush=True)
    addon_utils.enable("blender_mcp_addon")

    # Set unit system to Millimeters for CNC precision
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'
    scene.unit_settings.scale_length = 0.001

    print("[Blender GUI] Starting MCP Socket Server on 127.0.0.1:9876...", flush=True)
    res = bpy.ops.mcp.start_server()
    print(f"[Blender GUI] Server start result: {res}", flush=True)
    print("[Blender GUI] BLENDER_GUI_READY on 127.0.0.1:9876", flush=True)

if __name__ == "__main__":
    setup()
