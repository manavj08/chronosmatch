"""
run_dashboard_demo.py
------------------------
Day 7: one-command way to see the live curses dashboard with real
synthetic order flow, the same way run_demo.py shows the plain-text
version.

Starts two real OS processes:
  - a "generator" process (same as run_demo.py's), writing random
    orders into the shared-memory ring buffer, silently (no prints ---
    curses owns the terminal, mixing plain stdout writes into a
    curses screen corrupts the display)
  - the curses dashboard process (dashboard/live_dashboard.py),
    reading from that same buffer, matching with the real Cython
    engine, and rendering live

Run:
    python setup_demo.py       (one-time, builds the Cython extension)
    python run_dashboard_demo.py

Press Ctrl+C to exit early, or it stops on its own after
DEMO_DURATION_SECONDS.
"""

import curses
import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_check import require_compiled_engine
from shared.ring_buffer import RingBuffer
from shared.shared_memory import reset_shared_region
from simulator.order_generator import generate_order

DEMO_DURATION_SECONDS = 20
ORDERS_PER_SECOND = 8
RING_BUFFER_CAPACITY = 256


def generator_process():
    """Same role as run_demo.py's generator_process, but silent ---
    printing to stdout while curses owns the terminal would corrupt
    the dashboard's display."""
    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    interval = 1.0 / ORDERS_PER_SECOND
    end_time = time.time() + DEMO_DURATION_SECONDS

    while time.time() < end_time:
        order = generate_order()
        while rb.is_full():
            time.sleep(0.01)
        rb.write_order(order)
        time.sleep(interval)


def dashboard_process():
    from dashboard.live_dashboard import run_dashboard

    def _run(stdscr):
        run_dashboard(stdscr, ring_buffer_capacity=RING_BUFFER_CAPACITY,
                      duration_seconds=DEMO_DURATION_SECONDS)

    try:
        curses.wrapper(_run)
    except KeyboardInterrupt:
        pass






def report_exit_status(banner, **processes):
    """Print an honest summary and exit non-zero if any child crashed.

    These demos used to print "Both processes exited cleanly"
    unconditionally, without ever looking at an exit code. A child could
    die on an unhandled exception and the demo would still announce
    success --- which is exactly what happened when the Cython engine
    was missing: the matcher crashed on import, and the demo reported a
    clean finish regardless.
    """
    failures = {name: p.exitcode for name, p in processes.items() if p.exitcode != 0}

    print()
    print("=" * 70)
    if failures:
        print(f"{banner} FAILED.")
        for name, code in failures.items():
            print(f"  {name} process exited with code {code} "
                  f"(see its traceback above)")
        print("=" * 70)
        sys.exit(1)

    codes = ", ".join(f"{name} {p.exitcode}" for name, p in processes.items())
    print(f"{banner} All processes exited cleanly (exit codes: {codes}).")
    print("=" * 70)


def main():
    # reset_shared_region() removes leftovers from a previous run (both
    # the .mem file and its .lock) and releases the creating handle, so
    # the child processes are the only holders. Doing this by hand used
    # to miss the lock file and keep the mapping open, which on Windows
    # left files that could not be deleted or resized on the next run.
    # Check before starting any child process: the import failure
    # otherwise happens inside a child, as a traceback buried in the
    # output.
    require_compiled_engine()

    reset_shared_region(RING_BUFFER_CAPACITY)

    gen = multiprocessing.Process(target=generator_process, name="generator")
    dash = multiprocessing.Process(target=dashboard_process, name="dashboard")

    gen.start()
    dash.start()

    gen.join()
    dash.join()

    report_exit_status("Dashboard demo finished.", generator=gen, dashboard=dash)



if __name__ == "__main__":
    main()
