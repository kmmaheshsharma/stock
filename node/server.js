require("dotenv").config(); // Load environment variables

const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");
const { pool } = require("./db");
const { generateUserAlerts } = require("./alerts");
const { runSentimentCron } = require("./sentiment-cron"); // optional

const app = express();
app.use(express.json());

// Serve static chart files if needed
app.use("/chart", express.static(path.join(__dirname, "chart")));

const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*", // adjust to PWA domain in production
  },
});

// --------------------- SOCKET.IO ---------------------
const userSockets = {}; // userId -> socket

io.on("connection", (socket) => {
  console.log("Socket connected:", socket.id);

  socket.on("registerUser", ({ userId }) => {
    userSockets[userId] = socket;
    console.log(`User ${userId} registered for live alerts`);
  });

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

// --------------------- SEND MESSAGE ---------------------
function sendToBot(userId, text, chart = null) {
  const socket = userSockets[userId];
  if (!socket || socket.disconnected) return;
  socket.emit("alertMessage", { text, chart });
}

// --------------------- BACKGROUND ALERTS ---------------------
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

// Optional: timeout wrapper for Python calls inside generateUserAlerts
function withTimeout(promise, ms = 15000) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("Operation timed out")), ms)
    ),
  ]);
}

// --------------------- START BACKGROUND JOBS ---------------------
async function startBackgroundJobs() {
  console.log("⏱️ Starting background jobs");

  // 1️⃣ Run sentiment cron safely
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
    console.error("Initial alerts failed:", err);
  }

  // 3️⃣ Schedule periodic run every minute
  setInterval(async () => {
    try {
      await runAlertsForAllUsers();
      console.log("📨 Background alerts sent");
    } catch (err) {
      console.error("Background alerts job failed:", err);
    }
  }, 60 * 1000); // every 1 minute
}

// --------------------- EXPRESS ROUTES ---------------------
app.get("/", (req, res) => res.send("🚀 Server is up and running"));

// Add other API routes: /api/webchat, /api/alerts, /api/sentiments, /api/check-user, /api/users

// --------------------- START SERVER ---------------------
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);

  // Start background jobs AFTER server starts
  setTimeout(() => {
    startBackgroundJobs().catch((err) =>
      console.error("Background jobs failed:", err)
    );
  }, 2000);
});
