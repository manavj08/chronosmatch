import random
import time

from config import (
    PRICE_MIN,
    PRICE_MAX,
    MIN_QUANTITY,
    MAX_QUANTITY,
    BUY_PROBABILITY,
    SELL_PROBABILITY
)


class OrderGenerator:

    def __init__(self):
        self.order_id = 0

    def generate_order(self):
        """
        Generate a random BUY or SELL order.
        """

        # 1. Generate order side
        random_value = random.random()

        if random_value < BUY_PROBABILITY:
            side = "BUY"
        else:
            side = "SELL"

        # 2. Generate random price
        price = round(
            random.uniform(PRICE_MIN, PRICE_MAX),
            2
        )

        # 3. Generate random quantity
        quantity = random.randint(
            MIN_QUANTITY,
            MAX_QUANTITY
        )

        # 4. Generate timestamp
        timestamp = int(time.time() * 1000)

        # 5. Generate Order ID
        self.order_id += 1

        # Create order
        order = {
            "order_id": self.order_id,
            "side": side,
            "price": price,
            "quantity": quantity,
            "timestamp": timestamp
        }

        return order