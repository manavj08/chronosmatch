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
