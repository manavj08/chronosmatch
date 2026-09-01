"""
engine/
--------
Cython Price-Time Priority limit order book / matching engine.

Build first:
    cd engine
    python setup.py build_ext --inplace

Then:
    from engine import MatchingEngine
"""

try:
    from .matching_engine import MatchingEngine
    __all__ = ["MatchingEngine"]
except ImportError:
    # Extension not built yet. Importing `engine` for anything other than
    # running setup.py should still work without crashing at import time.
    __all__ = []
