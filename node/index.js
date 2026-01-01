// ================= ENV =================
require("dotenv").config();

// ================= CORE =================
const { spawn } = require("child_process");
const path = require("path");
const express = require("express");
const bodyParser = require("body-parser");

// ================= APP MODULES =================
const { pool } = require("./db");
const { handleMessage } = require("./routes");
const { runAlerts } = require("./alerts");

// ================= SENTIMENT UPDATE =================
function updateSentiment(symbol) {
  const scriptPath = path.join(__dirname, "../python/update_sentiment.py");
  const proc = spawn("python3", [scriptPath, symbol], {
    env: process.env,
  });

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

// Run sentiment cron once at startup
runSentimentCron();

// ================= EXPRESS APP =================
const app = express();
app.use(bodyParser.json());

console.log("VERIFY_TOKEN:", process.env.VERIFY_TOKEN);

// ================= PWA STATIC FILES =================
const publicPath = path.join(__dirname, "public");

// 🔎 DEBUG (keep for Railway logs)
console.log("DIRNAME:", __dirname);
console.log("PUBLIC PATH:", publicPath);

// Serve static assets
app.use(express.static(publicPath));

// ✅ ROOT ROUTE (CRITICAL FIX)
app.get("/", (req, res) => {
  res.sendFile(path.join(publicPath, "index.html"));
});

// ================= META WEBHOOK VERIFICATION (GET) =================
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

// ================= MESSAGE RECEIVER (POST) =================
app.post("/webhook", handleMessage);

// ================= SPA FALLBACK (AFTER WEBHOOK) =================
app.get("*", (req, res) => {
  res.sendFile(path.join(publicPath, "index.html"));
});

// ================= START SERVER =================
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 WhatsApp bot + PWA running on port ${PORT}`);
});

// ================= AUTO ALERT ENGINE =================
setInterval(runAlerts, 24 * 60 * 60 * 1000);
runAlerts();
