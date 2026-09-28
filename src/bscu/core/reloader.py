"""
Dynamic Hot-Reload module for BSCU Add-on.
Reloads all submodules in memory without restarting Blender.
"""

import importlib
import sys
from typing import List


def get_bscu_submodules() -> List[str]:
    """Retrieve all loaded modules belonging to the bscu package."""
    pkg_prefix = "bscu."
    modules = [name for name in sys.modules.keys() if name == "bscu" or name.startswith(pkg_prefix)]
    # Sort modules so parents are reloaded after children if needed
    return sorted(modules, key=lambda x: x.count("."), reverse=True)


def reload_bscu_modules() -> List[str]:
    """
    Perform hot-reload on all loaded BSCU submodules.
    Returns the list of successfully reloaded module names.
    """
    reloaded = []
    submodules = get_bscu_submodules()

    for mod_name in submodules:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            try:
                importlib.reload(mod)
                reloaded.append(mod_name)
            except Exception as e:
                print(f"[BSCU Reloader] Warning: Failed to reload {mod_name}: {e}")

    print(f"[BSCU Reloader] Successfully reloaded {len(reloaded)} module(s).")
    return reloaded
