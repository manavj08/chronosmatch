// ===================================
// WEBSOCKET SIMULATION
// ===================================

const socketMessages = [

    "Connected to Trading Server",

    "Receiving Live Market Data",

    "BTC Price Updated",

    "ETH Trade Executed",

    "Order Book Synced",

    "Latency Stable",

    "Portfolio Updated",

    "Market News Received",

    "Server Heartbeat OK",

    "WebSocket Connected"

];

function simulateWebSocket(){

    const message =
        socketMessages[Math.floor(Math.random()*socketMessages.length)];

    console.log("WebSocket:", message);

}

setInterval(simulateWebSocket,5000);