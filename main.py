from simulator.market_simulator import MarketSimulator


# Temporary Ring Buffer function
# Replace this with Member A's actual write_order()
def write_order(order):

    print("Ring Buffer received:", order)


# Create simulator
simulator = MarketSimulator(write_order)


# Start simulation
simulator.start_simulation()


# Keep program running
try:

    while True:
        pass

except KeyboardInterrupt:

    simulator.stop_simulation()

    print("Simulation stopped.")