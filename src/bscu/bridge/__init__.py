"""
Bridge package for BSCU. Modules here read and write Blender data on behalf of
the pure core.

Only modules that actually register Blender classes belong in MODULES; plain
read-only helpers are imported directly by their consumers.
"""

from . import snapshot  # noqa: F401  (re-exported for convenience)
