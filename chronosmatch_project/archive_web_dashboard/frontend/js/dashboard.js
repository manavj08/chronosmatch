document.getElementById("startBtn").onclick=function(){

alert("Trading Engine Started");

}

document.getElementById("pauseBtn").onclick=function(){

alert("Trading Engine Paused");

}

document.getElementById("resumeBtn").onclick=function(){

alert("Trading Engine Resumed");

}

document.getElementById("stopBtn").onclick=function(){

alert("Trading Engine Stopped");

}
// =====================
// Live Clock
// =====================

function updateClock() {

    const now = new Date();

    const options = {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric"
    };

    const date = now.toLocaleDateString("en-US", options);
    const time = now.toLocaleTimeString();

    document.getElementById("clock").innerHTML =
        date + " | " + time;
}

setInterval(updateClock, 1000);

updateClock();
// ===============================
// Live Dashboard Data
// ===============================

let orders = 5200;
let trades = 1800;
let latency = 45;
let buffer = 32;

const cards = document.querySelectorAll(".card h1");

function updateDashboard(){

    orders += Math.floor(Math.random()*8);

    trades += Math.floor(Math.random()*5);

    latency = 40 + Math.floor(Math.random()*10);

    buffer = 25 + Math.floor(Math.random()*15);

    cards[0].innerHTML = orders;

    cards[1].innerHTML = trades;

    cards[2].innerHTML = latency + " ms";

    cards[3].innerHTML = buffer + "%";

}

setInterval(updateDashboard,3000);
// ===============================
// LIVE ACTIVITY LOG
// ===============================

const activityLog = document.getElementById("activityLog");

const activities = [

    "BTC Buy Order Executed",

    "ETH Trade Completed",

    "New User Logged In",

    "Order Book Updated",

    "Price Alert Triggered",

    "Market Data Synced",

    "Trade Matched Successfully",

    "Portfolio Updated",

    "Server Connection Stable",

    "AAPL Stock Purchased"

];

function addActivity(){

    const li = document.createElement("li");

    const randomActivity =
        activities[Math.floor(Math.random() * activities.length)];

    const time = new Date().toLocaleTimeString();

    li.innerHTML = time + " - " + randomActivity;

    activityLog.prepend(li);

    if(activityLog.children.length > 10){

        activityLog.removeChild(activityLog.lastChild);

    }

}

setInterval(addActivity,3000);
// ==========================
// Search Recent Trades
// ==========================

const searchBox = document.getElementById("searchBox");

if (searchBox) {

    searchBox.addEventListener("keyup", function () {

        let value = this.value.toLowerCase();

        let rows = document.querySelectorAll(".table table tr");

        rows.forEach((row, index) => {

            if (index === 0) return;

            let text = row.innerText.toLowerCase();

            if (text.includes(value)) {

                row.style.display = "";

            } else {

                row.style.display = "none";

            }

        });

    });

}
// ==========================
// Dark / Light Theme
// ==========================

const themeBtn = document.getElementById("themeToggle");

if(themeBtn){

themeBtn.onclick = function(){

document.body.classList.toggle("light-theme");

if(document.body.classList.contains("light-theme")){

themeBtn.innerHTML="☀";

}else{

themeBtn.innerHTML="🌙";

}

}

}
// =====================================
// LIVE ORDER BOOK
// =====================================

const buyTable = document.getElementById("buyTable");
const sellTable = document.getElementById("sellTable");

function updateOrderBook(){

    // Buy Orders

    for(let i=1;i<buyTable.rows.length;i++){

        let price = 65100 + Math.floor(Math.random()*200);

        let qty = 1 + Math.floor(Math.random()*20);

        buyTable.rows[i].cells[0].innerHTML = "$" + price;
        buyTable.rows[i].cells[1].innerHTML = qty;

    }

    // Sell Orders

    for(let i=1;i<sellTable.rows.length;i++){

        let price = 65200 + Math.floor(Math.random()*200);

        let qty = 1 + Math.floor(Math.random()*20);

        sellTable.rows[i].cells[0].innerHTML = "$" + price;
        sellTable.rows[i].cells[1].innerHTML = qty;

    }

}

setInterval(updateOrderBook,2000);
// =====================================
// LIVE RECENT TRADES
// =====================================

const tradeTable = document.getElementById("tradeTable");

const stocks = [
    "BTC",
    "ETH",
    "AAPL",
    "TSLA",
    "MSFT",
    "NVDA",
    "GOOG",
    "AMZN"
];

function addTrade(){

    const row = tradeTable.insertRow(1);

    const timeCell = row.insertCell(0);
    const stockCell = row.insertCell(1);
    const priceCell = row.insertCell(2);
    const qtyCell = row.insertCell(3);

    const now = new Date();

    timeCell.innerHTML = now.toLocaleTimeString();

    const stock =
        stocks[Math.floor(Math.random()*stocks.length)];

    stockCell.innerHTML = stock;

    const price =
        (100 + Math.random()*70000).toFixed(2);

    priceCell.innerHTML = "$" + price;

    qtyCell.innerHTML =
        Math.floor(Math.random()*20)+1;

    while(tradeTable.rows.length > 11){

        tradeTable.deleteRow(tradeTable.rows.length-1);

    }

}

setInterval(addTrade,3000);
// =====================================
// LIVE MARKET NEWS
// =====================================

const newsList = document.querySelector(".news ul");

const newsUpdates = [

"📈 Bitcoin crosses $70,000",

"📉 Tesla shares drop 2%",

"🚀 NVIDIA stock reaches all-time high",

"💰 Gold prices increase 1.5%",

"🏦 Federal Reserve announces policy update",

"📊 Apple reports record quarterly earnings",

"🌍 Oil prices fall after global supply increase",

"💹 Ethereum gains 5% in one day",

"📢 Microsoft launches new AI platform",

"💵 US Dollar strengthens against Euro"

];

function updateNews(){

    const randomNews =
        newsUpdates[Math.floor(Math.random()*newsUpdates.length)];

    const firstItem = newsList.firstElementChild;

    firstItem.innerHTML = randomNews;

    newsList.appendChild(firstItem);

}

setInterval(updateNews,8000);
// ===============================
// ACTIVE SIDEBAR MENU
// ===============================

const menuItems = document.querySelectorAll(".sidebar a");

menuItems.forEach(item => {

    item.addEventListener("click", function(){

        menuItems.forEach(link=>link.classList.remove("active"));

        this.classList.add("active");

    });

});
// ===============================
// LOADING SCREEN
// ===============================

window.onload = function(){

    setTimeout(function(){

        document.getElementById("loader").style.display = "none";

    },2000);

};
// =======================================
// ADMIN DROPDOWN + NOTIFICATION PANEL
// =======================================

const adminBtn = document.getElementById("adminBtn");
const dropdownMenu = document.getElementById("dropdownMenu");

const notificationBtn = document.getElementById("notificationBtn");
const notificationPanel = document.getElementById("notificationPanel");

// Admin Menu

if(adminBtn && dropdownMenu){

    adminBtn.addEventListener("click",function(e){

        e.stopPropagation();

        dropdownMenu.style.display =
        dropdownMenu.style.display==="block" ? "none":"block";

        notificationPanel.style.display="none";

    });

}

// Notification

if(notificationBtn && notificationPanel){

    notificationBtn.addEventListener("click",function(e){

        e.stopPropagation();

        notificationPanel.style.display =
        notificationPanel.style.display==="block" ? "none":"block";

        dropdownMenu.style.display="none";

    });

}

// Close both when clicking outside

document.addEventListener("click",function(){

    if(dropdownMenu){

        dropdownMenu.style.display="none";

    }

    if(notificationPanel){

        notificationPanel.style.display="none";

    }

});
// ===============================
// Animated Counter
// ===============================

function animateCounter(element, start, end, duration) {

    let startTime = null;

    function update(currentTime) {

        if (!startTime) startTime = currentTime;

        const progress = Math.min((currentTime - startTime) / duration, 1);

        element.innerHTML = Math.floor(progress * (end - start) + start);

        if (progress < 1) {

            requestAnimationFrame(update);

        }

    }

    requestAnimationFrame(update);

}

window.addEventListener("load", function () {

    const cards = document.querySelectorAll(".card h1");

    animateCounter(cards[0], 0, 5200, 1200);

    animateCounter(cards[1], 0, 1800, 1200);

});