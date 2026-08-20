import sqlite3
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class SQLiteManager:

    def __init__(self, database_name="trades.db"):
        self.database_path = Path(__file__).resolve().parent / database_name
        self.create_table()

    def get_connection(self):
        return sqlite3.connect(self.database_path)

    def create_table(self):
        connection = self.get_connection()

        try:
            cursor = connection.cursor()

            cursor.execute("""
 CREATE TABLE IF NOT EXISTS trades (
                    trade_id INTEGER PRIMARY KEY,
                    buy_order_id INTEGER NOT NULL,
                    sell_order_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    matched_at INTEGER NOT NULL
                )
            """)

            connection.commit()

            logger.info("SQLite trades table created successfully")

        except sqlite3.Error as error:
            logger.error("Database error: %s", error)

        finally:
            connection.close()

    def save_trade(self, trade):
        connection = self.get_connection()

        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    trade_id,
                    buy_order_id,
                    sell_order_id,
                    price,
                    quantity,
                    matched_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                trade["trade_id"],
                trade["buy_order_id"],
                trade["sell_order_id"],
                trade["price"],
                trade["quantity"],
                trade["matched_at"]
            ))

            connection.commit()

            logger.info(
                "Trade Stored - Trade #%s",
                trade["trade_id"]
                            )

            return True

        except sqlite3.Error as error:
            logger.error("Failed to save trade: %s", error)
            return False

        finally:
            connection.close()

    def get_recent_trades(self, limit=10):
        connection = self.get_connection()

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    trade_id,
                    buy_order_id,
                    sell_order_id,
                    price,
                    quantity,
                    matched_at
                FROM trades
                 ORDER BY trade_id DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()

            return [
                {
                    "trade_id": row[0],
                    "buy_order_id": row[1],
                    "sell_order_id": row[2],
                    "price": row[3],
                    "quantity": row[4],
                    "matched_at": row[5]
                }
                for row in rows
            ]

        except sqlite3.Error as error:
            logger.error("Failed to read recent trades: %s", error)
            return []
        finally:
            connection.close()

    def get_trade_history(self):
        connection = self.get_connection()

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    trade_id,
                    buy_order_id,
                    sell_order_id,
                    price,
                    quantity,
                    matched_at
                FROM trades
                ORDER BY trade_id ASC
            """)

            rows = cursor.fetchall()

            return [
                {
                    "trade_id": row[0],
                    "buy_order_id": row[1],
                    "sell_order_id": row[2],
                    "price": row[3],
                    "quantity": row[4],
                    "matched_at": row[5]
                }
                for row in rows
            ]

        except sqlite3.Error as error:
            logger.error("Failed to read trade history: %s", error)
            return []

        finally:
            connection.close()

    def get_statistics(self):
        connection = self.get_connection()

        try:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*),
                    COALESCE(SUM(quantity), 0),
                    COALESCE(AVG(price), 0)
                FROM trades
            """)

            row = cursor.fetchone()

            return {
                "total_trades": row[0],
                "total_volume": row[1],
                "average_price": round(row[2], 2)
            }

        except sqlite3.Error as error:
            logger.error("Failed to calculate statistics: %s", error)

            return {
                "total_trades": 0,
                 "total_volume": 0,
                "average_price": 0
            }

        finally:
            connection.close()

    def clear_database(self):
        connection = self.get_connection()

        try:
            cursor = connection.cursor()

            cursor.execute("DELETE FROM trades")

            connection.commit()

            logger.info("Trade database cleared")

            return True

        except sqlite3.Error as error:
            logger.error("Failed to clear database: %s", error)
            return False

        finally:
            connection.close()