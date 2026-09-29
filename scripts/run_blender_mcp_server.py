"""
Headless runner script for Blender MCP Server.
Starts blender_mcp_addon socket server and services requests in a non-blocking loop.
"""

import signal
import sys
import time

import addon_utils
import bpy


def main():
    print("[MCP Runner] Enabling blender_mcp_addon...", flush=True)
    loaded, enabled = addon_utils.check("blender_mcp_addon")
    if not enabled:
        addon_utils.enable("blender_mcp_addon")

    print("[MCP Runner] Starting MCP socket server...", flush=True)
    res = bpy.ops.mcp.start_server()
    if res != {'FINISHED'}:
        print(f"[MCP Runner] Failed to start server: {res}", file=sys.stderr, flush=True)
        sys.exit(1)

    from blender_mcp_addon import get_server
    server = get_server()
    if not server or not server.is_running:
        print("[MCP Runner] Server instance is not running!", file=sys.stderr, flush=True)
        sys.exit(1)

    print(f"[MCP Runner] BLENDER_MCP_READY on {server.host}:{server.port}", flush=True)

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print("[MCP Runner] Received shutdown signal...", flush=True)
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while running and server.is_running:
            server._tick()
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        print("[MCP Runner] Shutting down MCP server...", flush=True)
        server.stop()
        print("[MCP Runner] Blender exiting cleanly.", flush=True)

if __name__ == "__main__":
    main()
