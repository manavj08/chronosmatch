"""
setup_demo.py
--------------
Run this ONCE before run_demo.py. Builds the Cython matching engine
(matching_engine/order_book.pyx) into a real compiled extension.

This is just a convenience wrapper around:
    cd matching_engine && python setup.py build_ext --inplace
"""

import subprocess
import sys
import os

MATCHING_ENGINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matching_engine")


def main():
    print("Building the Cython matching engine...")
    result = subprocess.run(
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        cwd=MATCHING_ENGINE_DIR,
    )
    if result.returncode != 0:
        print("\nBuild failed. Make sure a C compiler is installed:")
        print("  - Windows: Visual Studio Build Tools, 'Desktop development with C++'")
        print("  - Linux: sudo apt install build-essential")
        print("  - macOS: xcode-select --install")
        sys.exit(1)

    print("\nBuild succeeded. You can now run: python run_demo.py")


if __name__ == "__main__":
    main()
