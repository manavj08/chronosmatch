"""
dashboard/tests/test_dashboard_logic.py
------------------------------------------
Day 7: tests for the parts of dashboard/live_dashboard.py that can be
tested without a real terminal --- whale-trade detection and
formatting, and safe_addstr-style bounds behavior conceptually
(the actual curses rendering itself cannot run headless in this
sandbox; that was verified manually via a pseudo-tty session, see
CHANGELOG.md's Day 7 entry for how and what was observed).

curses.wrapper() requires cbreak()/nocbreak() terminal control that
fails outside a real TTY (confirmed: this sandbox has none). Rather
than skip dashboard testing entirely, the actual decision-making
logic (which trades count as "whale" trades, how the rolling history
is maintained) was extracted into pure functions with no curses
dependency, specifically so it COULD be unit tested here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.live_dashboard import (
    WHALE_THRESHOLD,
    format_latency_line,
    format_whale_line,
    update_whale_lines,
)


def make_trade(trade_id, buy_id, sell_id, price, quantity):
    return {
        "trade_id": trade_id,
        "buy_order_id": buy_id,
        "sell_order_id": sell_id,
        "price": price,
        "quantity": quantity,
    }


def make_latency_stats(count=100, p50_ns=500, p95_ns=900, p99_ns=1500, p999_ns=3000,
                        min_ns=200, mean_ns=600, max_ns=5000):
    return {
        "count": count, "min_ns": min_ns, "mean_ns": mean_ns, "max_ns": max_ns,
        "p50_ns": p50_ns, "p95_ns": p95_ns, "p99_ns": p99_ns, "p999_ns": p999_ns,
    }


def test_format_latency_line_shows_microseconds_not_nanoseconds():
    """The spec's stated display unit is microseconds -- this is the
    core requirement the dashboard's latency display exists to
    satisfy, so the unit conversion itself gets a direct test rather
    than just checking that some numbers appear."""
    stats = make_latency_stats(p50_ns=1500, p95_ns=2500, p99_ns=4000, p999_ns=8000)
    line = format_latency_line(stats)
    assert "1.5" in line   # 1500ns -> 1.5us
    assert "2.5" in line   # 2500ns -> 2.5us
    assert "4.0" in line   # 4000ns -> 4.0us
    assert "8.0" in line   # 8000ns -> 8.0us
    assert "us" in line.lower()


def test_format_latency_line_includes_all_four_percentiles():
    stats = make_latency_stats()
    line = format_latency_line(stats)
    assert "p50" in line
    assert "p95" in line
    assert "p99" in line
    assert "p999" in line


def test_format_latency_line_includes_sample_count():
    stats = make_latency_stats(count=12345)
    line = format_latency_line(stats)
    assert "12,345" in line or "12345" in line


def test_format_latency_line_handles_empty_book_without_crashing():
    """get_latency_stats() returns all-zero fields with count == 0 for
    an empty book (see matching_engine/order_book.pyx) -- the display
    function must handle that gracefully rather than showing a
    misleading '0.0us' latency (which would read as 'the system is
    infinitely fast' rather than 'no trades have happened yet')."""
    stats = make_latency_stats(count=0, p50_ns=0, p95_ns=0, p99_ns=0, p999_ns=0,
                                min_ns=0, mean_ns=0, max_ns=0)
    line = format_latency_line(stats)
    assert "no trades" in line.lower()
    assert "0.0" not in line  # must not present a fake zero-latency reading


def test_format_latency_line_percentiles_are_correctly_ordered_in_a_realistic_sample():
    """Sanity check with realistic, non-trivial values that the
    formatted line reflects p50 <= p95 <= p99 <= p999 in the order
    they're displayed (a transcription-order regression guard, not a
    re-test of the engine's own percentile math, which is covered in
    matching_engine/tests/test_latency_metrics.py)."""
    stats = make_latency_stats(p50_ns=800, p95_ns=1600, p99_ns=3200, p999_ns=6400)
    line = format_latency_line(stats)
    p50_pos = line.index("p50")
    p95_pos = line.index("p95")
    p99_pos = line.index("p99=")  # distinguish from "p999"
    p999_pos = line.index("p999")
    assert p50_pos < p95_pos < p99_pos < p999_pos


def test_format_whale_line_shape():
    trade = make_trade(1, 10, 20, 101.5, 75)
    line = format_whale_line(trade)
    assert "75" in line
    assert "101.50" in line
    assert "#10" in line
    assert "#20" in line
    assert line.startswith("WHALE:")


def test_update_whale_lines_ignores_small_trades():
    small_trade = make_trade(1, 1, 2, 100.0, WHALE_THRESHOLD - 1)
    result = update_whale_lines([], [small_trade])
    assert result == []


def test_update_whale_lines_includes_threshold_trade():
    """Quantity exactly at the threshold should count (>=, not >)."""
    trade = make_trade(1, 1, 2, 100.0, WHALE_THRESHOLD)
    result = update_whale_lines([], [trade])
    assert len(result) == 1


def test_update_whale_lines_newest_first():
    trade_a = make_trade(1, 1, 2, 100.0, 60)
    trade_b = make_trade(2, 3, 4, 101.0, 70)

    result = update_whale_lines([], [trade_a])
    result = update_whale_lines(result, [trade_b])

    assert "70" in result[0]  # most recent whale trade is first
    assert "60" in result[1]


def test_update_whale_lines_caps_at_max_lines():
    trades = [make_trade(i, i, i + 1, 100.0, 100) for i in range(10)]
    result = update_whale_lines([], trades, max_lines=3)
    assert len(result) == 3


def test_update_whale_lines_mixed_batch_only_keeps_whales():
    small = make_trade(1, 1, 2, 100.0, 5)
    big = make_trade(2, 3, 4, 100.0, 80)
    result = update_whale_lines([], [small, big])
    assert len(result) == 1
    assert "80" in result[0]


def test_update_whale_lines_empty_trades_no_change():
    existing = ["WHALE: 60 @ 100.00  (buy #1 x sell #2)"]
    result = update_whale_lines(existing, [])
    assert result == existing
