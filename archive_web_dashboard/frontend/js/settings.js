// ==========================
// LIVE CLOCK
// ==========================

function updateClock() {
    const clock = document.getElementById("clock");

    if (!clock) return;

    const now = new Date();

    const date = now.toLocaleDateString("en-US", {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric"
    });

    const time = now.toLocaleTimeString();

    clock.textContent = `${date} | ${time}`;
}

setInterval(updateClock, 1000);
updateClock();


// ==========================
// GET ELEMENTS
// ==========================

const saveSettings = document.getElementById("saveSettings");
const resetSettings = document.getElementById("resetSettings");
const settingsMessage = document.getElementById("settingsMessage");

const username = document.getElementById("username");
const email = document.getElementById("email");

const darkMode = document.getElementById("darkMode");

const orderNotifications =
    document.getElementById("orderNotifications");

const tradeNotifications =
    document.getElementById("tradeNotifications");

const systemAlerts =
    document.getElementById("systemAlerts");

const tradingSymbol =
    document.getElementById("tradingSymbol");

const updateInterval =
    document.getElementById("updateInterval");

const liveData =
    document.getElementById("liveData");

const autoLogs =
    document.getElementById("autoLogs");


// ==========================
// SHOW MESSAGE
// ==========================

function showMessage(message) {

    if (!settingsMessage) return;

    settingsMessage.textContent = message;
    settingsMessage.classList.add("show");

    setTimeout(function () {
        settingsMessage.classList.remove("show");
    }, 3000);
}


// ==========================
// DARK MODE
// ==========================

function applyDarkMode() {

    if (!darkMode) return;

    if (darkMode.checked) {
        document.body.classList.remove("light-mode");
    } else {
        document.body.classList.add("light-mode");
    }
}

if (darkMode) {

    darkMode.addEventListener("change", function () {
        applyDarkMode();
    });

}


// ==========================
// SAVE SETTINGS
// ==========================

if (saveSettings) {

    saveSettings.addEventListener("click", function () {

        const settings = {

            username: username.value,

            email: email.value,

            darkMode: darkMode.checked,

            orderNotifications:
                orderNotifications.checked,

            tradeNotifications:
                tradeNotifications.checked,

            systemAlerts:
                systemAlerts.checked,

            tradingSymbol:
                tradingSymbol.value,

            updateInterval:
                updateInterval.value,

            liveData:
                liveData.checked,

            autoLogs:
                autoLogs.checked
        };

        localStorage.setItem(
            "chronosMatchSettings",
            JSON.stringify(settings)
        );

        showMessage("✅ Settings saved successfully!");

    });

}


// ==========================
// LOAD SETTINGS
// ==========================

function loadSettings() {

    const savedSettings =
        localStorage.getItem("chronosMatchSettings");

    if (!savedSettings) {

        applyDarkMode();

        return;
    }

    try {

        const settings =
            JSON.parse(savedSettings);

        username.value =
            settings.username ?? "Admin";

        email.value =
            settings.email ??
            "admin@chronosmatch.com";

        darkMode.checked =
            settings.darkMode ?? true;

        orderNotifications.checked =
            settings.orderNotifications ?? true;

        tradeNotifications.checked =
            settings.tradeNotifications ?? true;

        systemAlerts.checked =
            settings.systemAlerts ?? true;

        tradingSymbol.value =
            settings.tradingSymbol ?? "BTC";

        updateInterval.value =
            settings.updateInterval ?? "3";

        liveData.checked =
            settings.liveData ?? true;

        autoLogs.checked =
            settings.autoLogs ?? true;

        applyDarkMode();

    } catch (error) {

        console.error(
            "Error loading settings:",
            error
        );

    }
}


// ==========================
// RESET SETTINGS
// ==========================

if (resetSettings) {

    resetSettings.addEventListener("click", function () {

        const confirmed = confirm(
            "Reset all settings to default?"
        );

        if (!confirmed) return;

        username.value = "Admin";

        email.value =
            "admin@chronosmatch.com";

        darkMode.checked = true;

        orderNotifications.checked = true;

        tradeNotifications.checked = true;

        systemAlerts.checked = true;

        tradingSymbol.value = "BTC";

        updateInterval.value = "3";

        liveData.checked = true;

        autoLogs.checked = true;

        localStorage.removeItem(
            "chronosMatchSettings"
        );

        applyDarkMode();

        showMessage(
            "🔄 Settings reset to default."
        );

    });

}


// ==========================
// START SETTINGS
// ==========================

loadSettings();