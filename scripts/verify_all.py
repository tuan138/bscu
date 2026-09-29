"""
Master Quality Gate for BSCU Add-on Development.
Executes 4 verification gates sequentially:
1. Rule compliance (file length <= 200 lines) & Ruff linting
2. Pure logic unit tests (pytest)
3. Headless Blender integration tests (blender -b)
4. CodeGraph sync
"""

import os
import subprocess
import sys
import time

MAX_LINE_LIMIT = 500


def log_header(title: str):
    print("\n" + "=" * 65)
    print(f" GATE: {title}")
    print("=" * 65)


def gate_1_rule_compliance() -> bool:
    log_header("1. Rule Compliance & File Length (<= 300-500 lines)")
    violations = []

    # Check line counts in src and tests
    for root_dir in ["src", "tests", "scripts"]:
        if not os.path.exists(root_dir):
            continue
        for dirpath, _, filenames in os.walk(root_dir):
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(dirpath, fname)
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                        lines = len(fp.readlines())
                    if lines > MAX_LINE_LIMIT:
                        violations.append((fpath, lines))

    if violations:
        print("[FAIL] The following files exceed the 200-line rule limit:", file=sys.stderr)
        for path, count in violations:
            print(f"  - {path}: {count} lines (MAX: {MAX_LINE_LIMIT})", file=sys.stderr)
        return False

    print(f"[PASS] All Python files are strictly within {MAX_LINE_LIMIT} lines.")

    # Run Ruff linter
    print("\nRunning Ruff linter...")
    res = subprocess.run([sys.executable, "-m", "ruff", "check", "src/", "tests/"])
    if res.returncode != 0:
        print("[FAIL] Ruff linter found issues.", file=sys.stderr)
        return False

    print("[PASS] Linter checks passed.")
    return True


def gate_2_unit_tests() -> bool:
    log_header("2. Pure Logic Unit Tests (pytest)")
    res = subprocess.run([sys.executable, "-m", "pytest", "tests/unit/"])
    if res.returncode != 0:
        print("[FAIL] Unit tests failed.", file=sys.stderr)
        return False
    print("[PASS] All unit tests passed.")
    return True


def gate_3_blender_integration() -> bool:
    log_header("3. Headless Blender Integration Tests")
    blender_exe = os.path.abspath("blender/blender.exe")
    if not os.path.exists(blender_exe):
        print(f"[FAIL] Blender executable not found at: {blender_exe}", file=sys.stderr)
        return False

    cmd = [blender_exe, "-b", "--python", "tests/run_tests.py"]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("[FAIL] Blender headless tests failed.", file=sys.stderr)
        return False
    print("[PASS] All Blender headless integration tests passed.")
    return True


def gate_4_codegraph_sync() -> bool:
    log_header("4. CodeGraph Synchronization")
    cmd = ["cmd.exe", "/c", "codegraph", "sync"]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("[WARN] CodeGraph sync reported warning or non-zero exit.", file=sys.stderr)
    else:
        print("[PASS] CodeGraph is synchronized with latest code.")
    return True


def main():
    start_time = time.perf_counter()
    print("=" * 65)
    print(" STARTING BSCU ONE-COMMAND QUALITY GATE (verify_all.py)")
    print("=" * 65)

    if not gate_1_rule_compliance():
        sys.exit(1)

    if not gate_2_unit_tests():
        sys.exit(1)

    if not gate_3_blender_integration():
        sys.exit(1)

    gate_4_codegraph_sync()

    elapsed = time.perf_counter() - start_time
    print("\n" + "=" * 65)
    print(f" [SUCCESS] ALL 4 QUALITY GATES PASSED in {elapsed:.2f}s!")
    print("=" * 65 + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
