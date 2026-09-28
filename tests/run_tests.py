"""
Master integration test runner for Blender headless environment.
Discovers and executes all test suites in tests/integration/.
"""

import importlib.util
import os
import sys


def run_all_integration_tests():
    print("=" * 60)
    print("STARTING BLENDER INTEGRATION TEST SUITE")
    print("=" * 60)

    test_dir = os.path.dirname(os.path.abspath(__file__))
    integration_dir = os.path.join(test_dir, "integration")

    if not os.path.exists(integration_dir):
        print(f"Directory not found: {integration_dir}", file=sys.stderr)
        sys.exit(1)

    test_files = [
        f
        for f in sorted(os.listdir(integration_dir))
        if f.startswith("test_") and f.endswith(".py")
    ]

    print(f"Found {len(test_files)} test suite(s): {', '.join(test_files)}\n")

    failed_suites = []

    for test_file in test_files:
        path = os.path.join(integration_dir, test_file)
        module_name = test_file[:-3]
        print(f"--> Running test suite: {test_file}")

        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            print(f"Failed to load spec for {test_file}", file=sys.stderr)
            failed_suites.append(test_file)
            continue

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
            # If the module has a run_test function, call it
            if hasattr(module, "run_test"):
                module.run_test()
            print(f"--> PASSED: {test_file}\n")
        except Exception as e:
            print(f"--> FAILED: {test_file} with error: {e}\n", file=sys.stderr)
            failed_suites.append(test_file)

    print("=" * 60)
    if failed_suites:
        print(
            f"INTEGRATION TESTS FAILED: {len(failed_suites)} suite(s) failed: {', '.join(failed_suites)}",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print("ALL BLENDER INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    run_all_integration_tests()
