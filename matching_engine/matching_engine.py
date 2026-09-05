class MatchingEngine:
    """
    Simple order matching engine.

    Matches BUY orders with SELL orders.

    A trade happens when:

        BUY price >= SELL price
    """

    def __init__(self):
        self.buy_orders = []
        self.sell_orders = []
        self.trades = []

    def add_order(self, order):
        """
        Add an order to the matching engine.
        """

        if order["side"] == "BUY":
            self.buy_orders.append(order)
        elif order["side"] == "SELL":
            self.sell_orders.append(order)

        else:
            raise ValueError("Order side must be BUY or SELL")

    def match_orders(self):
        """
        Match BUY and SELL orders.

        Returns executed trades.
        """

        executed_trades = []

        # Sort BUY orders from highest price
        self.buy_orders.sort(
            key=lambda order: order["price"],
            reverse=True
        )
        # Sort SELL orders from lowest price
        self.sell_orders.sort(
            key=lambda order: order["price"]
        )

        while self.buy_orders and self.sell_orders:

            best_buy = self.buy_orders[0]
            best_sell = self.sell_orders[0]

            # Check if prices can match
            if best_buy["price"] >= best_sell["price"]:

                trade_quantity = min(
                    best_buy["quantity"],
                    best_sell["quantity"]
                     )

                trade_price = best_sell["price"]

                trade = {
                    "buy_order_id": best_buy["order_id"],
                    "sell_order_id": best_sell["order_id"],
                    "price": trade_price,
                    "quantity": trade_quantity
                }

                executed_trades.append(trade)
                self.trades.append(trade)

                # Reduce quantities
                best_buy["quantity"] -= trade_quantity
                best_sell["quantity"] -= trade_quantity

                # Remove completed BUY order
                if best_buy["quantity"] == 0:
                    self.buy_orders.pop(0)

                # Remove completed SELL order
                if best_sell["quantity"] == 0:
                    self.sell_orders.pop(0)

            else:
                # No more possible matches
                break

        return executed_trades

    def get_trades(self):
        """
        Return all executed trades.
        """

        return self.trades