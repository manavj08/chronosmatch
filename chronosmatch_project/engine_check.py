"""
engine_check.py
------------------
One shared guard for "is the compiled Cython engine actually built?".

The matching engine is a C-extension compiled from
`matching_engine/order_book.pyx`. It is deliberately not committed to
git (`.gitignore` excludes `*.pyd` and `*.so`), so a fresh clone has to
build it once with `python setup_demo.py` --- HOW_TO_RUN.md step 2.

When that step is skipped, the failure used to surface as a bare
`ModuleNotFoundError` traceback at whatever point some script happened
to reach its `from order_book import OrderBookCython` line. In the
multi-process demos that point is inside a CHILD process, so the
traceback scrolled past under the generator's per-order logging and the
demo then printed a success banner anyway.

This module exists so every entry point checks the same way, in the
parent, before doing any work --- and so the fix only has to be written
once instead of being copy-pasted into each runner and drifting.
"""

import os
import sys


def require_compiled_engine(exit_on_missing: bool = True) -> bool:
    """Verify the compiled engine is importable.

    Prints an actionable message and exits 1 if it is not. Pass
    `exit_on_missing=False` to get a boolean back instead, for callers
    that want to degrade rather than stop.

    Returns True when the engine is available.
    """
    engine_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matching_engine")
    if os.path.isdir(engine_dir) and engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)

    try:
        import order_book  # noqa: F401  --- the compiled .pyd / .so
        return True
    except ImportError:
        pass

    print("=" * 70)
    print("The Cython matching engine has not been built yet.")
    print()
    print("The engine is a compiled C-extension, so it has to be built")
    print("before this script can run:")
    print()
    print("    python setup_demo.py")
    print()
    print("That needs a C compiler (Visual Studio Build Tools with the")
    print("'Desktop development with C++' workload on Windows). See")
    print("HOW_TO_RUN.md step 2 for the full instructions.")
    print("=" * 70)

    if exit_on_missing:
        sys.exit(1)
    return False
