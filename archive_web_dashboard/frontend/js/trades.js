// ==========================
// Live Clock
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
// Trade Counters
// ==========================

function updateTradeCounters() {

    const totalTrades = document.getElementById("totalTrades");
    const buyTrades = document.getElementById("buyTrades");
    const sellTrades = document.getElementById("sellTrades");

    if (!totalTrades || !buyTrades || !sellTrades) return;

    const buy = Math.floor(Math.random() * 80) + 220;
    const sell = Math.floor(Math.random() * 70) + 180;

    buyTrades.textContent = buy;
    sellTrades.textContent = sell;
    totalTrades.textContent = buy + sell;
}


// ==========================
// Start / Pause / Resume / Stop
// ==========================

const startBtn = document.getElementById("startBtn");
const pauseBtn = document.getElementById("pauseBtn");
const resumeBtn = document.getElementById("resumeBtn");
const stopBtn = document.getElementById("stopBtn");

let tradeInterval = null;


// Start

if (startBtn) {

    startBtn.addEventListener("click", function () {

        if (tradeInterval !== null) {
            clearInterval(tradeInterval);
        }

        updateTradeCounters();

        tradeInterval = setInterval(
            updateTradeCounters,
            3000
        );

    });

}


// Pause

if (pauseBtn) {

    pauseBtn.addEventListener("click", function () {

        if (tradeInterval !== null) {

            clearInterval(tradeInterval);

            tradeInterval = null;

        }

    });

}


// Resume

if (resumeBtn) {

    resumeBtn.addEventListener("click", function () {

        if (tradeInterval !== null) {
            clearInterval(tradeInterval);
        }

        updateTradeCounters();

        tradeInterval = setInterval(
            updateTradeCounters,
            3000
        );

    });

}


// Stop

if (stopBtn) {

    stopBtn.addEventListener("click", function () {

        if (tradeInterval !== null) {

            clearInterval(tradeInterval);

            tradeInterval = null;

        }

    });

}


// ==========================
// Notification Panel
// ==========================

const notificationBtn =
    document.getElementById("notificationBtn");

const notificationPanel =
    document.getElementById("notificationPanel");

if (notificationBtn && notificationPanel) {

    notificationBtn.addEventListener("click", function (event) {

        event.stopPropagation();

        notificationPanel.classList.toggle("show");

    });

}


// ==========================
// Admin Dropdown
// ==========================

const adminBtn =
    document.getElementById("adminBtn");

const dropdownMenu =
    document.getElementById("dropdownMenu");

if (adminBtn && dropdownMenu) {

    adminBtn.addEventListener("click", function (event) {

        event.stopPropagation();

        dropdownMenu.classList.toggle("show");

    });

}


// ==========================
// Close Panels
// ==========================

document.addEventListener("click", function () {

    if (notificationPanel) {
        notificationPanel.classList.remove("show");
    }

    if (dropdownMenu) {
        dropdownMenu.classList.remove("show");
    }

});


// ==========================
// Theme Toggle
// ==========================

const themeToggle =
    document.getElementById("themeToggle");

if (themeToggle) {

    themeToggle.addEventListener("click", function () {

        document.body.classList.toggle("light-mode");

        if (
            document.body.classList.contains("light-mode")
        ) {

            themeToggle.textContent = "☀️";

        } else {

            themeToggle.textContent = "🌙";

        }

    });

}


// ==========================
// Trade Search
// ==========================

const searchBox =
    document.getElementById("searchBox");

const tradesTable =
    document.getElementById("tradesTable");

if (searchBox && tradesTable) {

    searchBox.addEventListener("input", function () {

        const searchValue =
            searchBox.value.toLowerCase();

        const rows =
            tradesTable.querySelectorAll("tbody tr");

        rows.forEach(function (row) {

            const rowText =
                row.textContent.toLowerCase();

            if (rowText.includes(searchValue)) {

                row.style.display = "";

            } else {

                row.style.display = "none";

            }

        });

    });

}


// ==========================
// Start Trades Automatically
// ==========================

updateTradeCounters();

tradeInterval = setInterval(
    updateTradeCounters,
    3000
);