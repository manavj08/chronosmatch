"""
test_skeleton.py
-----------------
Quick smoke test for the Day 1 skeleton. Run this after setup to confirm
every module imports and the fake end-to-end flow works, before handing
files out to the team.

Run:  python -m unittest test_skeleton.py   -or-   pytest test_skeleton.py
"""

import time
import unittest

import shared_interface as bus
from order_book import OrderBook
from ring_buffer_stub import pack_order, unpack_order, RECORD_SIZE
from simulator_starter import make_random_order


class TestSharedInterface(unittest.TestCase):
    def setUp(self):
        bus._fake_buffer.clear()

    def test_write_then_read_order(self):
        order = {"order_id": bus.next_order_id(), "side": "B", "price": 100.0,
                  "quantity": 10, "timestamp": time.perf_counter_ns()}
        bus.write_order(order)
        self.assertEqual(bus.buffer_size(), 1)
        self.assertEqual(bus.read_order(), order)
        self.assertIsNone(bus.read_order())

    def test_write_order_rejects_missing_keys(self):
        with self.assertRaises(ValueError):
            bus.write_order({"order_id": 1, "side": "B"})


class TestOrderBook(unittest.TestCase):
    def setUp(self):
        bus._fake_buffer.clear()

    def test_process_next_moves_order_onto_book(self):
        book = OrderBook()
        bus.write_order({"order_id": bus.next_order_id(), "side": "B", "price": 101.0,
                          "quantity": 10, "timestamp": time.perf_counter_ns()})
        processed = book.process_next()
        self.assertIsNotNone(processed)
        self.assertEqual(len(book.buy_side), 1)
        self.assertIsNone(book.process_next())  # buffer now empty

    def test_get_top_levels_shape(self):
        book = OrderBook()
        levels = book.get_top_levels()
        self.assertIn("bids", levels)
        self.assertIn("asks", levels)


class TestRingBufferStub(unittest.TestCase):
    def test_pack_unpack_roundtrip(self):
        order = {"order_id": 1, "side": "B", "price": 101.25,
                  "quantity": 10, "timestamp": time.perf_counter_ns()}
        packed = pack_order(order)
        self.assertEqual(len(packed), RECORD_SIZE)
        self.assertEqual(unpack_order(packed), order)


class TestSimulator(unittest.TestCase):
    def test_make_random_order_has_required_keys(self):
        order = make_random_order()
        required = {"order_id", "side", "price", "quantity", "timestamp"}
        self.assertTrue(required.issubset(order))
        self.assertIn(order["side"], ("B", "S"))


if __name__ == "__main__":
    unittest.main()
