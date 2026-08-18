
import time
import logging
import threading

from simulator.order_generator import OrderGenerator
from config import ORDERS_PER_SECOND


# --------------------------------------------------
# Logging Configuration
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Market Simulator
# --------------------------------------------------

class MarketSimulator:

    def __init__(self, write_order):
        """
        write_order is provided by Member A.

        It sends generated orders to the Ring Buffer.
        """

        self.write_order = write_order

        self.order_generator = OrderGenerator()

        self.running = False
        self.paused = False

        self.thread = None

    # --------------------------------------------------
    # Generate one order
    # --------------------------------------------------

    def generate_order(self):

        order = self.order_generator.generate_order()

        logger.info(
            "Generated %s Order #%s",
            order["side"],
            order["order_id"]
        )

        # Send order to Ring Buffer
        self.write_order(order)

        return order

    # --------------------------------------------------
    # Start simulation
    # --------------------------------------------------

    def start_simulation(self):

        if self.running:
            logger.warning("Simulator already running")
            return

        self.running = True
        self.paused = False

        logger.info("Simulator Started")

        self.thread = threading.Thread(
            target=self._simulation_loop,
            daemon=True
        )

        self.thread.start()

    # --------------------------------------------------
    # Simulation Loop
    # --------------------------------------------------

    def _simulation_loop(self):

        delay = 1 / ORDERS_PER_SECOND

        while self.running:

            if not self.paused:

                try:
                    self.generate_order()

                except Exception as error:

                    logger.error(
                        "Error generating order: %s",
                        error
                    )

            time.sleep(delay)

    # --------------------------------------------------
    # Stop simulation
    # --------------------------------------------------

    def stop_simulation(self):

        if not self.running:
            logger.warning("Simulator is not running")
            return

        self.running = False
        self.paused = False

        logger.info("Simulator Stopped")

    # --------------------------------------------------
    # Pause simulation
    # --------------------------------------------------

    def pause_simulation(self):

        if not self.running:
            logger.warning(
                "Cannot pause. Simulator is not running"
            )
            return

        self.paused = True

        logger.info("Simulator Paused")

    # --------------------------------------------------
    # Resume simulation
    # --------------------------------------------------

    def resume_simulation(self):

        if not self.running:
            logger.warning(
                "Cannot resume. Simulator is not running"
            )
            return

        self.paused = False

        logger.info("Simulator Resumed")