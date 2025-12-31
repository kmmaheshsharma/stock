// === CRON: Update Twitter Sentiment Table ===
require("dotenv").config();

const { spawn } = require("child_process");
const path = require("path");
const express = require("express");
const bodyParser = require("body-parser");

const { pool } = require("./db");
const { handleMessage } = require("./routes");
const { runAlerts } = require("./alerts");

// ================= SENTIMENT UPDATE =================
function updateSentiment(symbol) {
  const args = [path.join(__dirname, "../python/update_sentiment.py"), symbol];
  const proc = spawn("python3", args, { env: process.env });

  let out = "";
  let err = "";

  proc.stdout.on("data", d => (out += d.toString()));
  proc.stderr.on("data", d => (err += d.toString()));

  proc.on("close", () => {
    if (err) console.error(`[SENTIMENT] ${symbol} stderr:\n${err}`);
    if (out) console.log(`[SENTIMENT] ${symbol} output:\n${out}`);
  });
}

// ================= FETCH SYMBOLS FROM DB =================
async function fetchSentimentSymbols() {
  const res = await pool.query(`
    SELECT DISTINCT symbol
    FROM watchlist
  `);

  return res.rows.map(r => r.symbol.toUpperCase());
}

// ================= CRON RUNNER =================
async function runSentimentCron() {
  try {
    const sentimentSymbols = await fetchSentimentSymbols();

    if (!sentimentSymbols.length) {
      console.log("[SENTIMENT] No symbols found in watchlist");
      return;
    }

    for (const symbol of sentimentSymbols) {
      updateSentiment(symbol);
    }
  } catch (e) {
    console.error("[SENTIMENT] Cron failed:", e);
  }
}

// Run every 15 minutes
setInterval(runSentimentCron, 10 * 60 * 1000);

// Run once at startup
runSentimentCron();

// ================= EXPRESS =================
const app = express();
app.use(bodyParser.json());

/**
 * ✅ META WEBHOOK VERIFICATION (GET)
 */
app.get("/webhook", (req, res) => {
  const mode = req.query["hub.mode"];
  const token = req.query["hub.verify_token"];
  const challenge = req.query["hub.challenge"];

  console.log("🔍 Webhook verification:", { mode, token });

  if (mode === "subscribe" && token === process.env.VERIFY_TOKEN) {
    console.log("✅ Webhook verified successfully");
    return res.status(200).send(challenge);
  } else {
    console.log("❌ Webhook verification failed");
    return res.sendStatus(403);
  }
});

/**
 * ✅ MESSAGE RECEIVER (POST)
 */
app.post("/webhook", handleMessage);

app.listen(3000, () => {
  console.log("🚀 WhatsApp bot running on port 3000");
});

/**
 * ✅ AUTO ALERT ENGINE
 */
setInterval(runAlerts, 10 * 60 * 1000);
runAlerts();
