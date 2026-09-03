import unittest

from simulator.ring_buffer import RingBuffer


class TestRingBuffer(unittest.TestCase):

    def test_add_item(self):

        buffer = RingBuffer(5)

        buffer.add("Order 1")

        self.assertEqual(len(buffer), 1)


    def test_buffer_capacity(self):

        buffer = RingBuffer(3)

        buffer.add("Order 1")
        buffer.add("Order 2")
        buffer.add("Order 3")
        self.assertEqual(len(buffer), 3)


    def test_overwrite_oldest_item(self):

        buffer = RingBuffer(3)

        buffer.add("Order 1")
        buffer.add("Order 2")
        buffer.add("Order 3")
        buffer.add("Order 4")

        recent = buffer.get_all()

        self.assertIn("Order 4", recent)
        self.assertNotIn("Order 1", recent)


    def test_get_recent_orders(self):

        buffer = RingBuffer(5)

        buffer.add("Order 1")
        buffer.add("Order 2")
        buffer.add("Order 3")

        recent = buffer.get_recent(2)

        self.assertEqual(len(recent), 2)

        self.assertEqual(recent[0], "Order 3")
        self.assertEqual(recent[1], "Order 2")


if __name__ == "__main__":
    unittest.main()