require("dotenv").config();
const path = require("path");
const express = require("express");
const bodyParser = require("body-parser");
const { spawn } = require("child_process");
const http = require("http");
const { Server } = require("socket.io");

const { pool } = require("./db");
const { handleMessage, handleChat } = require("./routes");
const { runAlerts } = require("./alerts");

const app = express();
app.use(bodyParser.json());

// ================= PWA STATIC FILES =================
const publicPath = path.join(__dirname, "public");
app.use(express.static(publicPath));

// ================= ROOT ROUTE =================
app.get("/", (req, res) => {
  res.sendFile(path.join(publicPath, "index.html"));
});

// ================= META WEBHOOK =================
app.get("/webhook", (req, res) => {
  const mode = req.query["hub.mode"];
  const token = req.query["hub.verify_token"];
  const challenge = req.query["hub.challenge"];

  if (mode === "subscribe" && token === process.env.VERIFY_TOKEN) {
    return res.status(200).send(challenge);
  }
  return res.sendStatus(403);
});

// ================= MESSAGE RECEIVER =================
// app.post("/webhook", handleMessage);

// ================= PWA API ROUTES =================
app.get("/api/sentiments", async (req, res) => {
  try {
    const rows = await pool.query(
      "SELECT symbol, sentiment_type, sentiment, change_percent FROM watchlist"
    );

    const data = rows.rows.map(r => {
      let percent = 50;
      if (r.sentiment_type === "accumulation") percent = 75;
      else if (r.sentiment_type === "distribution") percent = 25;

      const changePercent = parseFloat(r.change_percent) || 0;

      return {
        symbol: r.symbol,
        sentiment:
          r.sentiment_type === "accumulation"
            ? "Bullish"
            : r.sentiment_type === "distribution"
            ? "Bearish"
            : "Neutral",
        percent,
        change: `${changePercent.toFixed(2)}%`,
        trend:
          changePercent > 0
            ? "Trending Upward"
            : changePercent < 0
            ? "Trending Downward"
            : "Stable",
      };
    });

    res.json(data);
  } catch (err) {
    console.error("[API /sentiments]", err);
    res.status(500).json({ error: "Failed to fetch sentiments" });
  }
});

// POST /api/chat
app.post("/api/chat", handleChat);

// ================= SUBSCRIBE USER =================
// Mark user as subscribed in DB
app.post("/api/subscribe", async (req, res) => {
  try {
    const { userId } = req.body;
    if (!userId) return res.status(400).json({ error: "Missing userId" });

    await pool.query("UPDATE users SET subscribed=true WHERE id=$1", [userId]);
    res.json({ success: true });
  } catch (err) {
    console.error("[API /subscribe]", err);
    res.status(500).json({ error: "Failed to subscribe user" });
  }
});

// ================= HEALTH CHECK =================
app.get("/health", (req, res) => {
  res.json({ status: "ok", time: new Date().toISOString() });
});

// ================= SPA FALLBACK =================
app.use((req, res) => {
  res.sendFile(path.join(publicPath, "index.html"));
});

// ================= SOCKET.IO =================
const server = http.createServer(app);
const io = new Server(server);

const userSockets = {};

io.on("connection", (socket) => {
  const userId = socket.handshake.query.userId;
  if (userId) userSockets[userId] = socket;

  socket.on("disconnect", () => {
    delete userSockets[userId];
  });
});

// Helper to send alerts to PWA bot
function sendToBot(userId, text, chart) {
  const socket = userSockets[userId];
  if (!socket) return;
  socket.emit("alertMessage", { text, chart });
}

// ================= BACKGROUND JOBS =================

// Sentiment update
function updateSentiment(symbol) {
  try {
    const scriptPath = path.join(__dirname, "../python/update_sentiment.py");
    spawn("python3", [scriptPath, symbol], { env: process.env });
  } catch (err) {
    console.error("[updateSentiment]", err.message);
  }
}

async function fetchSentimentSymbols() {
  const res = await pool.query(`SELECT DISTINCT symbol FROM watchlist`);
  return res.rows.map(r => r.symbol.toUpperCase());
}

async function runSentimentCron() {
  try {
    const symbols = await fetchSentimentSymbols();
    for (const s of symbols) updateSentiment(s);
  } catch (e) {
    console.error("[SENTIMENT]", e.message);
  }
}

// Start background jobs
async function startBackgroundJobs() {
  console.log("⏱️ Starting background jobs");

  // 1️⃣ Run sentiment cron
  runSentimentCron();

  // 2️⃣ Run PWA/bot alerts (dryRun = true)
  const dryRunMessages = await runAlerts([], true);
  console.log("✅ DryRun alerts sent to bot:", dryRunMessages.length);

  // 3️⃣ Schedule WhatsApp alerts for subscribed users
  setInterval(async () => {
    await runAlerts([], true); // dryRun = false → WhatsApp
    console.log("📨 Background WhatsApp alerts sent to subscribed users");
  }, 1 * 60 * 60 * 1000); // every 4 hours
}

// ================= START SERVER =================
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  setTimeout(startBackgroundJobs, 3000);
});
