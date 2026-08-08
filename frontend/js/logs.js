// ==========================
// Logs - Live Clock
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
// Log Elements
// ==========================

const logTable = document.getElementById("logTable");
const logBody = logTable
    ? logTable.querySelector("tbody")
    : null;

const searchInput =
    document.getElementById("logSearch");

const filterSelect =
    document.getElementById("logFilter");

const clearButton =
    document.getElementById("clearLogs");

const totalLogs =
    document.getElementById("totalLogs");

const successLogs =
    document.getElementById("successLogs");

const warningLogs =
    document.getElementById("warningLogs");

const errorLogs =
    document.getElementById("errorLogs");


// ==========================
// Update Log Counts
// ==========================

function updateLogCounts() {

    if (!logBody) return;

    const rows = logBody.querySelectorAll("tr");

    let success = 0;
    let warning = 0;
    let error = 0;

    rows.forEach(function(row) {

        const level =
            row.cells[1]?.textContent
                .trim()
                .toLowerCase();

        if (level === "success") {
            success++;
        }

        if (level === "warning") {
            warning++;
        }

        if (level === "error") {
            error++;
        }

    });

    if (totalLogs) {
        totalLogs.textContent = rows.length;
    }

    if (successLogs) {
        successLogs.textContent = success;
    }

    if (warningLogs) {
        warningLogs.textContent = warning;
    }

    if (errorLogs) {
        errorLogs.textContent = error;
    }
}


// ==========================
// Search Logs
// ==========================

function filterLogs() {

    if (!logBody) return;

    const searchText =
        searchInput
            ? searchInput.value.toLowerCase()
            : "";

    const selectedFilter =
        filterSelect
            ? filterSelect.value.toLowerCase()
            : "all";

    const rows = logBody.querySelectorAll("tr");

    rows.forEach(function(row) {

        const rowText =
            row.textContent.toLowerCase();

        const level =
            row.cells[1]?.textContent
                .trim()
                .toLowerCase();

        const matchesSearch =
            rowText.includes(searchText);

        const matchesFilter =
            selectedFilter === "all" ||
            level === selectedFilter;

        if (matchesSearch && matchesFilter) {

            row.style.display = "";

        } else {

            row.style.display = "none";

        }

    });

}


// ==========================
// Search Event
// ==========================

if (searchInput) {

    searchInput.addEventListener(
        "input",
        filterLogs
    );

}


// ==========================
// Filter Event
// ==========================

if (filterSelect) {

    filterSelect.addEventListener(
        "change",
        filterLogs
    );

}


// ==========================
// Clear Logs
// ==========================

if (clearButton) {

    clearButton.addEventListener(
        "click",
        function() {

            if (!logBody) return;

            const confirmed =
                confirm(
                    "Are you sure you want to clear all logs?"
                );

            if (!confirmed) return;

            logBody.innerHTML = "";

            updateLogCounts();

        }
    );

}


// ==========================
// Live Log Generator
// ==========================

const logMessages = [

    {
        level: "SUCCESS",
        module: "Order Engine",
        message: "New buy order processed successfully"
    },

    {
        level: "SUCCESS",
        module: "Trade Engine",
        message: "Trade matched successfully"
    },

    {
        level: "SUCCESS",
        module: "WebSocket",
        message: "Live market data received"
    },

    {
        level: "WARNING",
        module: "Order Book",
        message: "High order volume detected"
    },

    {
        level: "WARNING",
        module: "System",
        message: "Buffer usage approaching limit"
    },

    {
        level: "ERROR",
        module: "API",
        message: "Temporary connection failure"
    }

];


// ==========================
// Add New Log
// ==========================

function addLiveLog() {

    if (!logBody) return;

    const randomIndex =
        Math.floor(
            Math.random() * logMessages.length
        );

    const log =
        logMessages[randomIndex];

    const now = new Date();

    const time =
        now.toLocaleTimeString();

    const row =
        document.createElement("tr");

    let statusClass = "success";

    if (log.level === "WARNING") {
        statusClass = "warning";
    }

    if (log.level === "ERROR") {
        statusClass = "error";
    }

    row.innerHTML = `
        <td>${time}</td>

        <td>
            <span class="${statusClass}">
                ${log.level}
            </span>
        </td>

        <td>${log.module}</td>

        <td>${log.message}</td>
    `;

    logBody.insertBefore(
        row,
        logBody.firstChild
    );


    // Keep only the latest 15 logs

    const rows =
        logBody.querySelectorAll("tr");

    if (rows.length > 15) {

        logBody.removeChild(
            rows[rows.length - 1]
        );

    }

    updateLogCounts();

    filterLogs();

}


// ==========================
// Start Live Logs
// ==========================

setInterval(
    addLiveLog,
    5000
);


// ==========================
// Initial Count
// ==========================

updateLogCounts();