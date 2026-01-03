require("dotenv").config();
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");
const { pool } = require("./db"); // PostgreSQL connection
const { generateUserAlerts } = require("./alerts");

const app = express();
app.use(express.json());

// Serve charts
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

// -------------------- SEND ALERT TO BOT --------------------
function sendToBot(userId, text, chart = null) {
  const socket = userSockets[userId];
  if (!socket || socket.disconnected) return;
  socket.emit("alertMessage", { text, chart });
}

// -------------------- BACKGROUND ALERT JOB --------------------
async function runAlertsForAllUsers() {
  try {
    const usersRes = await pool.query("SELECT id FROM users WHERE subscribed=true");

    await Promise.all(usersRes.rows.map(async (user) => {
      try {
        const messages = await Promise.race([
          generateUserAlerts(user),
          new Promise((_, reject) => setTimeout(() => reject(new Error("generateUserAlerts timeout")), 15000))
        ]);

        messages.forEach(msg => sendToBot(user.id, msg.text, msg.chart));
      } catch (err) {
        console.error(`Alerts failed for user ${user.id}:`, err.message);
      }
    }));

  } catch (err) {
    console.error("Failed fetching subscribed users:", err.message);
  }
}

function startBackgroundJobs() {
  console.log("⏱️ Background jobs started");
  // Initial run
  runAlertsForAllUsers().catch(err => console.error(err));
  // Schedule recurring run every minute
  setInterval(() => runAlertsForAllUsers().catch(err => console.error(err)), 60 * 1000);
}

// -------------------- EXPRESS ROUTES --------------------
app.get("/", (req, res) => res.send("🚀 Server is up"));
// Add /api/webchat, /api/alerts, /api/users, etc.

// -------------------- START SERVER --------------------
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);

  // Start background jobs async after server is ready
  setTimeout(() => startBackgroundJobs(), 1000);
});
