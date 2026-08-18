// ==========================
// Analytics - Live Clock
// ==========================

function updateClock() {

    const clock = document.getElementById("clock");

    if (!clock) return;

    const now = new Date();

    const options = {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric"
    };

    const date = now.toLocaleDateString("en-US", options);
    const time = now.toLocaleTimeString();

    clock.textContent = `${date} | ${time}`;
}

setInterval(updateClock, 1000);

updateClock();


// ==========================
// Analytics Live Statistics
// ==========================

function updateAnalytics() {

    const ordersProcessed =
        document.getElementById("ordersProcessed");

    const tradesMatched =
        document.getElementById("tradesMatched");

    const latency =
        document.getElementById("latency");

    const bufferUsage =
        document.getElementById("bufferUsage");

    const analyticsBuy =
        document.getElementById("analyticsBuy");

    const analyticsSell =
        document.getElementById("analyticsSell");

    const buyProgress =
        document.getElementById("buyProgress");

    const sellProgress =
        document.getElementById("sellProgress");


    // Orders Processed

    if (ordersProcessed) {

        const value =
            Math.floor(Math.random() * 100) + 5200;

        ordersProcessed.textContent = value;
    }


    // Trades Matched

    if (tradesMatched) {

        const value =
            Math.floor(Math.random() * 80) + 1800;

        tradesMatched.textContent = value;
    }


    // Average Latency

    if (latency) {

        const value =
            Math.floor(Math.random() * 15) + 40;

        latency.textContent = `${value} ms`;
    }


    // Buffer Usage

    if (bufferUsage) {

        const value =
            Math.floor(Math.random() * 20) + 20;

        bufferUsage.textContent = `${value}%`;
    }


    // Buy Orders

    if (analyticsBuy) {

        const value =
            Math.floor(Math.random() * 60) + 220;

        analyticsBuy.textContent = value;

        if (buyProgress) {
            buyProgress.style.width =
                `${Math.min(value / 4, 100)}%`;
        }
    }


    // Sell Orders

    if (analyticsSell) {

        const value =
            Math.floor(Math.random() * 50) + 180;

        analyticsSell.textContent = value;

        if (sellProgress) {
            sellProgress.style.width =
                `${Math.min(value / 4, 100)}%`;
        }
    }

}


// Update every 3 seconds

setInterval(updateAnalytics, 3000);

updateAnalytics();