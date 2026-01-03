require("dotenv").config();
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");
const { pool } = require("./db"); // your PostgreSQL connection
const { generateUserAlerts } = require("./alerts"); // alerts logic

const app = express();
app.use(express.json());

// Serve chart images
app.use("/chart", express.static(path.join(__dirname, "chart")));

const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" },
});

// -------------------- SOCKET.IO --------------------
const userSockets = {};

io.on("connection", (socket) => {
  console.log("Socket connected:", socket.id);

  socket.on("registerUser", ({ userId }) => {
    userSockets[userId] = socket;
    console.log(`User ${userId} registered`);
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

// -------------------- SEND TO BOT --------------------
function sendToBot(userId, text, chart = null) {
  const socket = userSockets[userId];
  if (!socket || socket.disconnected) return;
  socket.emit("alertMessage", { text, chart });
}

// -------------------- SAFE BACKGROUND JOB --------------------
async function runAlertsForAllUsers() {
  try {
    const usersRes = await pool.query("SELECT id FROM users WHERE subscribed=true");
    for (const user of usersRes.rows) {
      try {
        // Wrap in timeout to prevent blocking
        const messages = await Promise.race([
          generateUserAlerts(user),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("generateUserAlerts timeout")), 15000)
          ),
        ]);

        for (const msg of messages) {
          sendToBot(user.id, msg.text, msg.chart);
        }
      } catch (err) {
        console.error(`Alerts failed for user ${user.id}:`, err.message);
      }
    }
  } catch (err) {
    console.error("Failed fetching subscribed users:", err.message);
  }
}

// Start recurring alerts every 1 minute
function startBackgroundJobs() {
  console.log("⏱️ Starting background jobs");
  runAlertsForAllUsers(); // initial run
  setInterval(runAlertsForAllUsers, 60 * 1000);
}

// -------------------- EXPRESS ROUTES --------------------
app.get("/", (req, res) => res.send("🚀 Server is up"));

// Add other endpoints: /api/webchat, /api/alerts, etc.

// -------------------- START SERVER --------------------
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);

  // Start background jobs async, non-blocking
  setTimeout(() => startBackgroundJobs(), 2000);
});
