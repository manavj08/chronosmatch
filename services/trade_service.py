import logging

from database.sqlite_manager import SQLiteManager


logger = logging.getLogger(__name__)


class TradeService:

    def __init__(self):
        self.database = SQLiteManager()

    def save_trade(self, trade):
        return self.database.save_trade(trade)

    def get_recent_trades(self, limit=10):
        return self.database.get_recent_trades(limit)

    def get_trade_history(self):
        return self.database.get_trade_history()

    def get_statistics(self):
        return self.database.get_statistics()

    def clear_database(self):
        return self.database.clear_database()