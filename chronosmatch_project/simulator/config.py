"""
simulator/config.py
--------------------
MEMBER B'S CONFIGURATION.

Configurable values for the market simulator. Read by
order_generator.py / market_simulator.py rather than hardcoding
values inline, per the assignment spec.
"""

ORDERS_PER_SECOND = 100

PRICE_MIN = 100.0
PRICE_MAX = 105.0

MIN_QUANTITY = 1
MAX_QUANTITY = 100

BUY_PROBABILITY = 0.5   # SELL_PROBABILITY is just 1 - BUY_PROBABILITY
