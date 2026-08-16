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

from shared.ring_buffer import RingBuffer
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


def main():
    backing_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ring_buffer.mem")
    if os.path.exists(backing_file):
        os.remove(backing_file)

    RingBuffer(capacity=RING_BUFFER_CAPACITY, create=True)

    gen = multiprocessing.Process(target=generator_process, name="generator")
    dash = multiprocessing.Process(target=dashboard_process, name="dashboard")

    gen.start()
    dash.start()

    gen.join()
    dash.join()

    print("Dashboard demo finished. Both processes exited cleanly.")


if __name__ == "__main__":
    main()
