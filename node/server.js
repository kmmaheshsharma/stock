require("dotenv").config(); // load env once at the top

const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const { pool } = require("./db"); // your PostgreSQL pool
const { generateUserAlerts } = require("./alerts");
const { runSentimentCron } = require("./sentiment-cron"); // optional

const app = express();
app.use(express.json());

const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*", // adjust to your PWA domain in production
  },
});

// ================== SOCKET.IO ==================
const userSockets = {}; // userId -> socket

io.on("connection", (socket) => {
  console.log("Socket connected:", socket.id);

  // Register userId
  socket.on("registerUser", ({ userId }) => {
    userSockets[userId] = socket;
    console.log(`User ${userId} registered for live alerts`);
  });

  // Cleanup on disconnect
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

// ================== SEND MESSAGE ==================
function sendToBot(userId, text, chart = null) {
  const socket = userSockets[userId];
  if (!socket || socket.disconnected) return;
  socket.emit("alertMessage", { text, chart });
}

// ================== BACKGROUND ALERTS ==================
async function runAlertsForAllUsers() {
  try {
    const usersRes = await pool.query(
      "SELECT id FROM users WHERE subscribed=true"
    );

    for (const user of usersRes.rows) {
      try {
        const messages = await generateUserAlerts(user);

        for (const msg of messages) {
          sendToBot(user.id, msg.text, msg.chart);
        }
      } catch (e) {
        console.error("Error generating alerts for user", user.id, e);
      }
    }
  } catch (err) {
    console.error("Failed to fetch subscribed users:", err);
  }
}

// ================== START BACKGROUND JOBS ==================
async function startBackgroundJobs() {
  console.log("⏱️ Starting background jobs");

  // 1️⃣ Optional: sentiment cron
  try {
    runSentimentCron();
  } catch (err) {
    console.error("Sentiment cron failed:", err);
  }

  // 2️⃣ Initial run
  try {
    await runAlertsForAllUsers();
    console.log("📨 Initial background alerts sent");
  } catch (err) {
    console.error("Initial runAlertsForAllUsers failed:", err);
  }

  // 3️⃣ Scheduled run every minute
  setInterval(async () => {
    try {
      await runAlertsForAllUsers();
      console.log("📨 Background alerts sent");
    } catch (err) {
      console.error("Background alerts job failed:", err);
    }
  }, 60 * 1000);
}

// ================== EXPRESS ROUTES (example) ==================
app.get("/", (req, res) => {
  res.send("🚀 Server is up and running");
});

// ================== START SERVER ==================
const PORT = process.env.PORT || 3000;
server.listen(PORT, async () => {
  console.log(`🚀 Server running on port ${PORT}`);

  // Start background jobs after server is listening
  setTimeout(() => {
    startBackgroundJobs().catch((err) =>
      console.error("Background jobs failed:", err)
    );
  }, 3000);
});
