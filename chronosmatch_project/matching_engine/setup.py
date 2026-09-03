"""
matching_engine/setup.py
--------------------------
Build script for the Cython matching engine. Compiles order_book.pyx
into a real C-extension (.so on Linux/macOS, .pyd on Windows).

Usage:
    cd matching_engine
    python setup.py build_ext --inplace

This produces order_book.<platform-tag>.so (or .pyd) next to this
file, importable as `from matching_engine.order_book import
OrderBookCython` just like any other Python module --- except the
compiled parts run as C, not bytecode.
"""

from setuptools import setup, Extension
from Cython.Build import cythonize

setup(
    name="chronosmatch_matching_engine",
    ext_modules=cythonize(
        [Extension("order_book", ["order_book.pyx"])],
        compiler_directives={"language_level": "3"},
        annotate=True,  # generates order_book.html showing Python vs C lines
    ),
    zip_safe=False,
)
