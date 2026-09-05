import unittest
from matching_engine.matching_engine import MatchingEngine


class TestMatchingEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MatchingEngine()

    def test_add_buy_order(self):
        order = {
            "order_id": 1,
            "side": "BUY",
            "price": 100,
            "quantity": 10
        }

        self.engine.add_order(order)

        self.assertEqual(
            len(self.engine.buy_orders),
            1
        )
    def test_add_sell_order(self):
        order = {
            "order_id": 2,
            "side": "SELL",
            "price": 100,
            "quantity": 10
        }

        self.engine.add_order(order)

        self.assertEqual(
            len(self.engine.sell_orders),
            1
        )

    def test_matching_orders(self):

        buy_order = {
            "order_id": 1,
            "side": "BUY",
            "price": 100,
            "quantity": 10
        }
        sell_order = {
            "order_id": 2,
            "side": "SELL",
            "price": 100,
            "quantity": 10
        }

        self.engine.add_order(buy_order)
        self.engine.add_order(sell_order)

        trades = self.engine.match_orders()

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["price"], 100)
        self.assertEqual(trades[0]["quantity"], 10)

    def test_no_match(self):

        buy_order = {
            "order_id": 1,
            "side": "BUY",
            "price": 90,
            "quantity": 10
         }

        sell_order = {
            "order_id": 2,
            "side": "SELL",
            "price": 110,
            "quantity": 10
        }

        self.engine.add_order(buy_order)
        self.engine.add_order(sell_order)

        trades = self.engine.match_orders()

        self.assertEqual(len(trades), 0)


if __name__ == "__main__":
    unittest.main()