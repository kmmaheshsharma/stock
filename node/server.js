const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const { pool } = require("./db"); // your PostgreSQL pool
const { generateUserAlerts } = require("./alerts"); // your existing logic

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*", // adjust for your PWA domain
  },
});

// --- Track connected users ---
const userSockets = {}; // userId -> socket

io.on("connection", (socket) => {
  console.log("Socket connected:", socket.id);

  // User sends their userId to register
  socket.on("registerUser", ({ userId }) => {
    userSockets[userId] = socket;
    console.log(`User ${userId} registered for live alerts`);
  });

  // Remove user on disconnect
  socket.on("disconnect", () => {
    for (const [id, s] of Object.entries(userSockets)) {
      if (s.id === socket.id) {
        delete userSockets[id];
        console.log(`User ${id} disconnected`);
        break;
      }
    }
  });
});

// --- Send message to a user ---
function sendToBot(userId, text, chart = null) {
  const socket = userSockets[userId];
  if (!socket) return; // user offline
  socket.emit("alertMessage", { text, chart });
}

// --- Run alerts for all users ---
async function runAlertsForAllUsers() {
  const usersRes = await pool.query(
    "SELECT id FROM users WHERE subscribed=true"
  );

  for (const user of usersRes.rows) {
    const messages = await generateUserAlerts(user);

    for (const msg of messages) {
      sendToBot(user.id, msg.text, msg.chart);
    }
  }
}

// --- Background jobs ---
async function startBackgroundJobs() {
  console.log("⏱️ Starting background jobs");

  // 1️⃣ Run sentiment cron (if any)
  runSentimentCron();

  // 2️⃣ Run alerts immediately
  await runAlertsForAllUsers();

  // 3️⃣ Schedule every minute
  setInterval(async () => {
    await runAlertsForAllUsers();
    console.log("📨 Background alerts sent");
  }, 60 * 1000);
}

// --- Start server ---
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  setTimeout(startBackgroundJobs, 3000);
});
