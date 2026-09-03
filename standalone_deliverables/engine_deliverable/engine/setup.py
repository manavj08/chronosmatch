"""
engine/setup.py
-----------------
Build script for the Cython matching engine. Compiles matching_engine.pyx
into a real C-extension (.so on Linux/macOS, .pyd on Windows).

Usage:
    cd engine
    python setup.py build_ext --inplace

This produces matching_engine.<platform-tag>.so (or .pyd) next to this
file, importable as `from matching_engine import MatchingEngine`.

Requires Cython and a C compiler (gcc / clang / MSVC):
    pip install cython
"""

from setuptools import setup, Extension
from Cython.Build import cythonize

setup(
    name="chronosmatch_matching_engine",
    ext_modules=cythonize(
        [Extension("matching_engine", ["matching_engine.pyx"])],
        compiler_directives={"language_level": "3"},
    ),
    zip_safe=False,
)
