"""
simulator/tests/test_order_generator.py
-----------------------------------------
Day 2: tests for generate_order() --- correct shape, price range,
quantity range, and unique/incrementing order ids.
"""

from simulator import config
from simulator.order_generator import generate_order


def test_generated_order_has_required_keys():
    order = generate_order()
    assert set(order.keys()) == {
        "order_id", "side", "price", "quantity", "timestamp"
    }


def test_side_is_buy_or_sell():
    for _ in range(20):
        order = generate_order()
        assert order["side"] in ("B", "S")


def test_price_within_configured_range():
    for _ in range(50):
        order = generate_order()
        assert config.PRICE_MIN <= order["price"] <= config.PRICE_MAX


def test_quantity_within_configured_range():
    for _ in range(50):
        order = generate_order()
        assert config.MIN_QUANTITY <= order["quantity"] <= config.MAX_QUANTITY


def test_order_ids_increment():
    first = generate_order()
    second = generate_order()
    assert second["order_id"] > first["order_id"]
