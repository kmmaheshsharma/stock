require("dotenv").config();

const { spawn } = require("child_process");
const path = require("path");
const express = require("express");
const bodyParser = require("body-parser");

const { pool } = require("./db");
const { handleMessage } = require("./routes");
const { runAlerts } = require("./alerts");

const app = express();
app.use(bodyParser.json());

// ================= PWA STATIC FILES =================
const publicPath = path.join(__dirname, "public");

console.log("DIRNAME:", __dirname);
console.log("PUBLIC PATH:", publicPath);

app.use(express.static(publicPath));

// ✅ ROOT ROUTE
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

app.post("/webhook", handleMessage);

// ================= SPA FALLBACK (EXPRESS 5 SAFE) =================
app.get("/*", (req, res) => {
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
  const scriptPath = path.join(__dirname, "../python/update_sentiment.py");
  spawn("python3", [scriptPath, symbol], { env: process.env });
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
  runAlerts();
  setInterval(runAlerts, 24 * 60 * 60 * 1000);
}
