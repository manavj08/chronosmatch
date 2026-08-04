"""
dashboard_starter.py
---------------------
MEMBER C'S STARTING POINT (Beginner-friendly).

A live terminal UI using `curses`. Today it displays FAKE hardcoded
numbers so you can build and polish the layout without waiting for
anyone else's real code to exist.

Day 5: swap the FAKE section below for real calls into the Leader's
OrderBook (get_top_levels(), get_last_trade()) --- the display code
(the curses drawing part) does not need to change at all.
"""

import curses


def get_fake_order_book_snapshot() -> dict:
    """
    FAKE data standing in for order_book.get_top_levels() and
    order_book.get_last_trade().

    Day 5: replace this function's body with:
        from order_book import OrderBook
        book = OrderBook()  # the real shared instance
        levels = book.get_top_levels()
        last_trade = book.get_last_trade()
        return {"bids": levels["bids"], "asks": levels["asks"],
                "last_trade": last_trade}

    Keep the same return shape so draw_dashboard() below needs zero changes.
    """
    return {
        "bids": [{"price": 100.5, "quantity": 20}, {"price": 100.4, "quantity": 15}],
        "asks": [{"price": 100.6, "quantity": 10}, {"price": 100.7, "quantity": 25}],
        "last_trade": {"price": 100.55, "quantity": 5},
        "orders_processed": 1234,
        "trades_matched": 87,
        "latency_us": {"min": 12.3, "max": 88.1, "avg": 34.7},
    }


def draw_dashboard(stdscr):
    curses.curs_set(0)      # hide the blinking cursor
    stdscr.nodelay(True)    # don't block waiting for keypresses
    stdscr.timeout(100)     # refresh ~10x/second

    while True:
        stdscr.erase()
        data = get_fake_order_book_snapshot()

        stdscr.addstr(0, 0, "ChronosMatch --- Live Order Book", curses.A_BOLD)
        stdscr.addstr(2, 0, "BIDS", curses.A_BOLD)
        stdscr.addstr(2, 20, "ASKS", curses.A_BOLD)

        for i, (bid, ask) in enumerate(zip(data["bids"], data["asks"])):
            stdscr.addstr(3 + i, 0, f"{bid['price']:>8.2f} x{bid['quantity']}")
            stdscr.addstr(3 + i, 20, f"{ask['price']:>8.2f} x{ask['quantity']}")

        row = 3 + max(len(data["bids"]), len(data["asks"])) + 1
        lt = data["last_trade"]
        stdscr.addstr(row, 0, f"Last trade: {lt['price']:.2f} x{lt['quantity']}")

        row += 2
        stdscr.addstr(row, 0, f"Orders processed: {data['orders_processed']}")
        stdscr.addstr(row + 1, 0, f"Trades matched: {data['trades_matched']}")

        lat = data["latency_us"]
        row += 3
        stdscr.addstr(
            row, 0,
            f"Latency (us) --- min: {lat['min']:.1f} avg: {lat['avg']:.1f} max: {lat['max']:.1f}"
        )
        stdscr.addstr(row + 2, 0, "Press Ctrl+C to exit", curses.A_DIM)

        stdscr.refresh()
        key = stdscr.getch()
        if key == 3:  # Ctrl+C
            break


if __name__ == "__main__":
    try:
        curses.wrapper(draw_dashboard)
    except KeyboardInterrupt:
        pass
    print("Dashboard closed cleanly.")

# ----------------------------------------------------------------------
# WHAT TO DO NEXT:
#
# Day 2 -> replace hardcoded numbers above with a slightly bigger fake
#          dict (more rows) to make sure the layout still looks right.
# Day 3 -> add the latency line (already included above as a placeholder).
# Day 4 -> ask the Leader what get_top_levels() actually returns once
#          it's real, so the field names above match exactly.
# Day 5 -> swap get_fake_order_book_snapshot() for the real thing.
#          The draw_dashboard() function should need NO changes.
# Day 7 -> add whale-order highlighting: if a trade's quantity is above
#          some threshold, print that line with curses.A_REVERSE or a
#          color pair instead of plain text.
# ----------------------------------------------------------------------
