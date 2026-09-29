"""
Verify the packaged extension installs and enables in a real Blender.

This is the only test that catches packaging regressions: the archive layout is
what Blender's installer accepts, and the add-on must register its panels from
the installed copy rather than from the source tree.

Registration state is read from ``bpy.types`` because Python keeps the class
objects alive in ``__subclasses__()`` after an unregister.
"""

import os
import sys

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVE = os.path.join(REPO_ROOT, "dist", "bscu-1.0.0.zip")
BSCU_MODULE = "bscu"

EXPECTED_PANELS = {
    "BSCU_PT_steps",
    "BSCU_PT_stock",
    "BSCU_PT_caro",
    "BSCU_PT_layout",
    "BSCU_PT_relief",
}


def _registered_panels() -> set:
    """Panels Blender actually registered: each must exist under bpy.types."""
    return {name for name in dir(bpy.types) if name in EXPECTED_PANELS}


def test_archive_exists():
    assert os.path.exists(ARCHIVE), (
        f"Extension archive missing: {ARCHIVE}. Run scripts/package_extension.py first."
    )
    print(f"[OK] archive present: {ARCHIVE}")


def test_running_inside_blender():
    assert "blender" in bpy.app.binary_path.lower(), bpy.app.binary_path
    print(f"[OK] running inside Blender: {bpy.app.binary_path}")


def test_install_and_enable_extension():
    result = bpy.ops.preferences.addon_install(filepath=ARCHIVE, overwrite=True)
    assert "FINISHED" in result, result

    bpy.ops.preferences.addon_enable(module=BSCU_MODULE)
    enabled = {m.module for m in bpy.context.preferences.addons}
    assert BSCU_MODULE in enabled, sorted(enabled)
    print(f"[OK] installed and enabled {BSCU_MODULE}")


def test_installed_copy_registers_all_panels():
    missing = EXPECTED_PANELS - _registered_panels()
    assert not missing, f"Panels missing after install: {sorted(missing)}"
    print(f"[OK] installed panels: {sorted(_registered_panels())}")


def test_installed_core_stays_free_of_bpy():
    """core/ must remain import-free of bpy after packaging."""
    module = sys.modules.get(f"{BSCU_MODULE}.core.workflow")
    assert module is not None, "core.workflow not importable from the installed copy"
    with open(module.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert "import bpy" not in source, "core/workflow.py must not import bpy"
    print("[OK] core.workflow ships without a bpy import")


def test_disable_unregisters_every_panel():
    """Disabling must leave no BSCU panel behind; addon_remove needs a UI area."""
    bpy.ops.preferences.addon_disable(module=BSCU_MODULE)
    assert not _registered_panels(), f"Panels survived disable: {_registered_panels()}"

    bpy.ops.preferences.addon_enable(module=BSCU_MODULE)
    assert _registered_panels() == EXPECTED_PANELS, sorted(_registered_panels())
    print("[OK] disable removes panels, enable restores them")


def run_test():
    test_archive_exists()
    test_running_inside_blender()
    test_install_and_enable_extension()
    test_installed_copy_registers_all_panels()
    test_installed_core_stays_free_of_bpy()
    test_disable_unregisters_every_panel()
    print("\nExtension packaging verified end to end!")
