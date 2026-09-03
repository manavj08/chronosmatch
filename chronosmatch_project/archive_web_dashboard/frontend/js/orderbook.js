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
// Live Order Counter
// ==========================

function randomOrders() {

    const buyCount = document.getElementById("buyCount");
    const sellCount = document.getElementById("sellCount");
    const executedCount = document.getElementById("executedCount");

    if (buyCount) {
        buyCount.textContent =
            Math.floor(Math.random() * 80) + 220;
    }

    if (sellCount) {
        sellCount.textContent =
            Math.floor(Math.random() * 70) + 180;
    }

    if (executedCount) {
        executedCount.textContent =
            Math.floor(Math.random() * 120) + 430;
    }
}




// ==========================
// Notification Panel
// ==========================

const notificationBtn =
    document.getElementById("notificationBtn");

const notificationPanel =
    document.getElementById("notificationPanel");

if (notificationBtn && notificationPanel) {

    notificationBtn.addEventListener("click", function () {

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

    adminBtn.addEventListener("click", function () {

        dropdownMenu.classList.toggle("show");

    });

}


// ==========================
// Close Dropdowns
// ==========================

document.addEventListener("click", function (event) {

    if (
        notificationBtn &&
        notificationPanel &&
        !notificationBtn.contains(event.target) &&
        !notificationPanel.contains(event.target)
    ) {

        notificationPanel.classList.remove("show");

    }


    if (
        adminBtn &&
        dropdownMenu &&
        !adminBtn.contains(event.target) &&
        !dropdownMenu.contains(event.target)
    ) {

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
// Start / Pause / Resume / Stop
// ==========================

const startBtn =
    document.getElementById("startBtn");

const pauseBtn =
    document.getElementById("pauseBtn");

const resumeBtn =
    document.getElementById("resumeBtn");

const stopBtn =
    document.getElementById("stopBtn");

let orderUpdatesRunning = true;

let orderInterval =
    setInterval(randomOrders, 3000);


// Start

if (startBtn) {

    startBtn.addEventListener("click", function () {

        clearInterval(orderInterval);

        orderInterval =
            setInterval(randomOrders, 3000);

        orderUpdatesRunning = true;

    });

}


// Pause

if (pauseBtn) {

    pauseBtn.addEventListener("click", function () {

        clearInterval(orderInterval);

        orderUpdatesRunning = false;

    });

}


// Resume

if (resumeBtn) {

    resumeBtn.addEventListener("click", function () {

        clearInterval(orderInterval);

        orderInterval =
            setInterval(randomOrders, 3000);

        orderUpdatesRunning = true;

    });

}


// Stop

if (stopBtn) {

    stopBtn.addEventListener("click", function () {

        clearInterval(orderInterval);

        orderUpdatesRunning = false;

    });

}