"""
Package BSCU as an installable Blender extension.

An installable archive must contain a single root folder holding the add-on:
``bscu/blender_manifest.toml`` plus ``bscu/__init__.py`` and the sub-packages.
Blender 5.2's ``--command extension build`` writes a flat archive that its own
installer rejects ("__init__.py should be in a directory, not at top-level"), so
the archive is written here and checked by tests/integration/test_extension_install.py.
"""

import os
import sys
import tomllib
import zipfile

EXTENSION_ID = "bscu"
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def _log(message: str) -> None:
    print(f"[Package] {message}")


def _blender_exe() -> str:
    return os.path.abspath(os.path.join("blender", "blender.exe"))


def read_version(package_dir: str) -> str:
    """Take the version from the manifest so the archive name stays truthful."""
    with open(os.path.join(package_dir, "blender_manifest.toml"), "rb") as handle:
        return tomllib.load(handle)["version"]


def _iter_package_files(package_dir: str):
    """Yield (absolute_path, path_inside_archive) for every shipped file."""
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            if name.endswith(SKIP_SUFFIXES) or name == "blender_manifest.toml":
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, package_dir).replace(os.sep, "/")
            yield full, f"{EXTENSION_ID}/{rel}"


def build_archive(package_dir: str, output_dir: str) -> str:
    """Write dist/bscu-<version>.zip with the layout Blender installs."""
    version = read_version(package_dir)
    os.makedirs(output_dir, exist_ok=True)
    archive = os.path.join(output_dir, f"{EXTENSION_ID}-{version}.zip")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = os.path.join(package_dir, "blender_manifest.toml")
        zf.write(manifest, f"{EXTENSION_ID}/blender_manifest.toml")
        for full, target in _iter_package_files(package_dir):
            zf.write(full, target)
    return archive


def verify_archive(archive: str) -> None:
    """Fail loudly if the archive lacks the files an install needs."""
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())

    required = {
        f"{EXTENSION_ID}/blender_manifest.toml",
        f"{EXTENSION_ID}/__init__.py",
    }
    missing = required - names
    if missing:
        raise SystemExit(f"[FAIL] Archive missing {sorted(missing)}")

    stray = [n for n in names if "/" not in n]
    if stray:
        raise SystemExit(f"[FAIL] Files outside the add-on root: {stray}")

    _log(f"Archive layout verified: {len(names)} files under {EXTENSION_ID}/")


def validate_manifest(package_dir: str) -> bool:
    """Let Blender's own validator parse the manifest."""
    blender = _blender_exe()
    if not os.path.exists(blender):
        _log("WARN: Blender not found, skipping manifest validation")
        return True

    import subprocess

    result = subprocess.run(
        [blender, "--command", "extension", "validate", package_dir]
    )
    return result.returncode == 0


def main() -> int:
    package_dir = os.path.abspath(os.path.join("src", EXTENSION_ID))
    output_dir = os.path.abspath("dist")

    if not validate_manifest(package_dir):
        print("[FAIL] Manifest validation failed.", file=sys.stderr)
        return 1

    archive = build_archive(package_dir, output_dir)
    verify_archive(archive)

    size_kb = os.path.getsize(archive) / 1024
    print(f"\n[SUCCESS] Packaged {os.path.basename(archive)} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
