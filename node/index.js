require("dotenv").config();

const { spawn } = require("child_process");
const path = require("path");
const express = require("express");
const bodyParser = require("body-parser");

const { pool } = require("./db");
const { handleMessage, handleChat } = require("./routes");
const { runAlerts } = require("./alerts");
const { runPythonEngine, buildWhatsAppMessage } = require("./utils"); // helpers for chat API

const app = express();
app.use(bodyParser.json());

// ================= PWA STATIC FILES =================
const publicPath = path.join(__dirname, "public");
console.log("DIRNAME:", __dirname);
console.log("PUBLIC PATH:", publicPath);
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
app.post("/webhook", handleMessage);

// ================= PWA API ROUTES =================

// GET /api/sentiments
app.get("/api/sentiments", async (req, res) => {
  try {
    const rows = await pool.query(
      "SELECT symbol, sentiment_type, sentiment, change_percent FROM watchlist"
    );

    const data = rows.rows.map(r => {
      let percent = 50;
      if (r.sentiment_type === "accumulation") percent = 75;
      else if (r.sentiment_type === "distribution") percent = 25;

      const changePercent = parseFloat(r.change_percent) || 0; // ensure numeric

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
// ---------------- POST /api/chat ----------------
app.post("/api/chat", async (req, res) => {
  try {
    const { message } = req.body;
    if (!message) return res.status(400).json({ error: "No message provided" });

    // Call handleMessage for all messages
    const reply = await handleChat(message);

    // Send response
    res.json({
      text: reply.text,
      chart: reply.chart || null
    });

  } catch (err) {
    console.error("[API /chat]", err);
    res.status(500).json({ error: "Chat engine error" });
  }
});

// ================= HEALTH CHECK =================
app.get("/health", (req, res) => {
  res.json({ status: "ok", time: new Date().toISOString() });
});

// ================= SPA FALLBACK (EXPRESS 5 FIX) =================
// 🚨 Must be after all API routes
app.use((req, res) => {
  res.sendFile(path.join(publicPath, "index.html"));
});

// ================= START SERVER =================
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  setTimeout(startBackgroundJobs, 3000);
});

// ================= BACKGROUND JOBS =================
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

function startBackgroundJobs() {
  console.log("⏱️ Starting background jobs");
  runSentimentCron();
  runAlerts([]); // pass empty array to avoid errors
  setInterval(() => runAlerts([]), 1 * 60 * 1000);
}

// ================= SUBSCRIPTIONS (IN-MEMORY) =================
const subscriptions = [];

app.post("/api/subscribe", async (req, res) => {
  const sub = req.body;
  subscriptions.push(sub);
  res.json({ success: true });
});
