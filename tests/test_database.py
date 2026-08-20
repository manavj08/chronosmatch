import unittest
import time

from database.sqlite_manager import SQLiteManager


class TestDatabase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.database = SQLiteManager("test_trades.db")

    def setUp(self):
        self.database.clear_database()

    def test_save_trade(self):

        trade = {
            "trade_id": 1,
            "buy_order_id": 101,
            "sell_order_id": 102,
            "price": 101.50,
            "quantity": 25,
            "matched_at": int(time.time())
        }

        result = self.database.save_trade(trade)

        self.assertTrue(result)

    def test_get_recent_trades(self):

        trade = {
            "trade_id": 2,
            "buy_order_id": 103,
            "sell_order_id": 104,
            "price": 102.25,
            "quantity": 30,
            "matched_at": int(time.time())
        }

        self.database.save_trade(trade)

        trades = self.database.get_recent_trades(5)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["trade_id"], 2)
def test_get_trade_history(self):

        trade1 = {
            "trade_id": 3,
            "buy_order_id": 105,
            "sell_order_id": 106,
            "price": 100.50,
            "quantity": 10,
            "matched_at": int(time.time())
        }

        trade2 = {
            "trade_id": 4,
            "buy_order_id": 107,
            "sell_order_id": 108,
            "price": 103.50,
            "quantity": 20,
            "matched_at": int(time.time())
        }

        self.database.save_trade(trade1)
        self.database.save_trade(trade2)
        history = self.database.get_trade_history()

        self.assertEqual(len(history), 2)

def test_get_statistics(self):

        trade1 = {
            "trade_id": 5,
            "buy_order_id": 109,
            "sell_order_id": 110,
            "price": 100.00,
            "quantity": 10,
            "matched_at": int(time.time())
        }

        trade2 = {
            "trade_id": 6,
            "buy_order_id": 111,
            "sell_order_id": 112,
            "price": 102.00,
            "quantity": 20,
            "matched_at": int(time.time())
        }
        self.database.save_trade(trade1)
        self.database.save_trade(trade2)

        statistics = self.database.get_statistics()

        self.assertEqual(statistics["total_trades"], 2)
        self.assertEqual(statistics["total_volume"], 30)
        self.assertEqual(statistics["average_price"], 101.00)

def test_clear_database(self):

        trade = {
            "trade_id": 7,
            "buy_order_id": 113,
            "sell_order_id": 114,
            "price": 101.00,
            "quantity": 15,
            "matched_at": int(time.time())
        }

        self.database.save_trade(trade)

        result = self.database.clear_database()

        self.assertTrue(result)

        statistics = self.database.get_statistics()

        self.assertEqual(statistics["total_trades"], 0)


if __name__ == "__main__":
    unittest.main()