import time

from simulator.market_simulator import MarketSimulator


# Temporary Ring Buffer function
def write_order(order):
    print("ORDER:", order)


# Create simulator
simulator = MarketSimulator(write_order)


print("\n--- STARTING SIMULATOR ---")

simulator.start_simulation()

# Generate orders for 5 seconds
time.sleep(5)


print("\n--- PAUSING SIMULATOR ---")

simulator.pause_simulation()

# Stay paused for 5 seconds
time.sleep(5)


print("\n--- RESUMING SIMULATOR ---")

simulator.resume_simulation()

# Generate orders again for 5 seconds
time.sleep(5)


print("\n--- STOPPING SIMULATOR ---")

simulator.stop_simulation()

print("\nTest completed.")