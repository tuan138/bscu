"""
Packaging script for BSCU Blender Extension.
Validates blender_manifest.toml and builds dist/bscu-{version}.zip.
"""

import os
import sys
import subprocess


def package_extension():
    blender_exe = os.path.abspath("blender/blender.exe")
    source_dir = os.path.abspath("src/bscu")
    output_dir = os.path.abspath("dist")

    if not os.path.exists(blender_exe):
        print(f"[FAIL] Blender executable not found at: {blender_exe}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print("--> 1. Validating extension manifest...")
    val_cmd = [blender_exe, "--command", "extension", "validate", source_dir]
    val_res = subprocess.run(val_cmd)
    if val_res.returncode != 0:
        print("[FAIL] Extension validation failed.", file=sys.stderr)
        sys.exit(1)

    print("--> 2. Building extension archive...")
    build_cmd = [
        blender_exe,
        "--command",
        "extension",
        "build",
        "--source-dir",
        source_dir,
        "--output-dir",
        output_dir,
    ]
    build_res = subprocess.run(build_cmd)
    if build_res.returncode != 0:
        print("[FAIL] Extension build failed.", file=sys.stderr)
        sys.exit(1)

    zip_files = [f for f in os.listdir(output_dir) if f.endswith(".zip")]
    print(f"\n[SUCCESS] Successfully packaged {len(zip_files)} extension(s):")
    for zf in zip_files:
        fsize = os.path.getsize(os.path.join(output_dir, zf)) / 1024
        print(f"  - dist/{zf} ({fsize:.1f} KB)")


if __name__ == "__main__":
    package_extension()
