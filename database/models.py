class Trade:
    def __init__(
        self,
        trade_id=None,
        buy_order_id=None,
        sell_order_id=None,
        price=0.0,
        quantity=0,
        matched_at=None
    ):
        self.trade_id = trade_id
        self.buy_order_id = buy_order_id
        self.sell_order_id = sell_order_id
        self.price = price
        self.quantity = quantity
        self.matched_at = matched_at

    def to_dict(self):
        return {
            "trade_id": self.trade_id,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "price": self.price,
            "quantity": self.quantity,
            "matched_at": self.matched_at
        }