const { pool } = require("./db");
const { sendWhatsApp, sendWhatsAppImage } = require("./whatsapp");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const chartDir = path.join(__dirname, "chart");

// Ensure chart folder exists
if (!fs.existsSync(chartDir)) {
  fs.mkdirSync(chartDir);
}

// Thresholds for automatic exit suggestion
const PROFIT_THRESHOLD = 5; // 5% profit
const LOSS_THRESHOLD = 5;   // 5% loss
const BUY_DOWN_THRESHOLD = -2; // minor loss to consider adding shares

// --- Helper to calculate aggregated position for multiple purchases ---
function calculateAggregatedPosition(rows) {
  let totalQuantity = 0;
  let weightedEntry = 0;

  for (const row of rows) {
    totalQuantity += row.quantity;
    weightedEntry += row.entry_price * row.quantity;
  }

  const avgEntryPrice = totalQuantity > 0 ? weightedEntry / totalQuantity : 0;
  return { totalQuantity, avgEntryPrice };
}

// --- Helper to run Python engine and parse JSON ---
function runPythonEngine(message) {
  return new Promise((resolve) => {
    const enginePath = path.join(__dirname, "../python/engine.py");

    const py = spawn("python3", [enginePath, message], {
      env: process.env
    });

    let output = "";

    py.stdout.on("data", data => {
      output += data.toString();
    });

    py.stderr.on("data", err => {
      console.error("Python error:", err.toString());
    });

    py.on("close", code => {
      if (code === 0) {
        try {
          resolve(JSON.parse(output.trim()));
        } catch (e) {
          console.error("Python JSON parse error:", output);
          resolve(null);
        }
      } else {
        resolve(null);
      }
    });
  });
}

// --- Handle chat messages (greetings included) ---
async function processMessage(message) {
  if (!message) return "Please type something!";

  const greetings = ["hi", "hello", "hey", "hii"];
  const trimmedMessage = message.toLowerCase().trim();
  if (greetings.includes(trimmedMessage)) {
    console.log(`[GREETINGS] User said: "${message}"`);
    return "Hello! 👋 How can I help you today?";
  }

  console.log(`[SYMBOL] Processing symbol: ${message}`);
  const result = await runPythonEngine(message);

  // --- Check if Python engine returned anything ---
  if (!result) {
    console.warn(`[SYMBOL] No result from Python engine for: ${message}`);
    return `❌ Could not fetch stock info for "${message}". Try again later.`;
  }

  // --- Check if symbol is valid ---
  if (!result.symbol || (Array.isArray(result.alerts) && result.alerts.includes("invalid_symbol"))) {
    console.warn(`[SYMBOL] Invalid or unknown symbol: ${message}`);
    return `❌ Unable to fetch stock data for "${message}"`;
  }

  console.log(`[SYMBOL] Valid symbol received: ${result.symbol}`);

  // --- Build the WhatsApp-style message safely ---
  let msgText = `📊 *${result.symbol}* Update\n\n`;
  msgText += `💰 Price: ₹${result.price ?? "N/A"}\n`;

  if (result.low !== undefined && result.high !== undefined) {
    msgText += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}\n`;
  }

  if (result.volume !== undefined && result.avg_volume !== undefined) {
    const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
    msgText += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume.toFixed(0)}\n`;
  }

  if (result.change_percent !== undefined) {
    const changeEmoji =
      result.change_percent > 0 ? "🔺" : result.change_percent < 0 ? "🔻" : "➖";
    msgText += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%\n`;
  }

  let sentimentEmoji = "🧠";
  if (result.sentiment_type === "accumulation") sentimentEmoji = "🟢";
  if (result.sentiment_type === "distribution") sentimentEmoji = "🔴";
  if (result.sentiment_type === "hype") sentimentEmoji = "🚀";

  msgText += `${sentimentEmoji} Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "UNKNOWN"} (${result.sentiment ?? 0})\n\n`;

  let recommendation = result.recommendation || "Wait / Monitor";
  if (result.suggested_entry) {
    const lower = result.suggested_entry.lower ?? "N/A";
    const upper = result.suggested_entry.upper ?? "N/A";
    recommendation += ` | Suggested entry: ₹${lower} - ₹${upper}`;
  }
  msgText += `⚡ Recommendation: *${recommendation}*\n`;

  if (!Array.isArray(result.alerts) || result.alerts.length === 0) {
    msgText += `⚠️ No strong signal yet\n📌 Stock is in watch mode`;
  } else {
    msgText += `🚨 Alerts:\n`;
    for (const alert of result.alerts) {
      if (alert === "profit") msgText += `• 📈 Profit booking zone\n`;
      if (alert === "loss") msgText += `• 📉 Stoploss breached\n`;
      if (alert === "buy_signal") msgText += `• 🟢 Accumulation detected\n`;
      if (alert === "trap_warning") msgText += `• 🚨 Hype trap risk\n`;
      if (alert === "error") msgText += `• ⚠️ Error fetching data\n`;
      // No invalid_symbol here because we already filtered above
    }
  }

  // Optional: send chart if exists
  // if (result.chart) {
  //   await sendWhatsAppImage(msg.from || msg.phone, result.chart, `📊 ${result.symbol} Price Chart`);
  // }

  console.log(`[SYMBOL] Response ready for symbol: ${result.symbol}`);
  return msgText;
}

// --- Main alert runner for users ---
async function runAlerts(extraSymbols = []) {
  const users = await pool.query("SELECT id, phone FROM users");

  for (const user of users.rows) {
    const watchlistRes = await pool.query(
      "SELECT symbol FROM watchlist WHERE user_id=$1",
      [user.id]
    );
    const watchlist = watchlistRes.rows.map(w => w.symbol.toUpperCase());
    const allSymbols = [...new Set([...watchlist, ...extraSymbols])];

    for (const symbol of allSymbols) {
      const portfolioRes = await pool.query(
        "SELECT id, entry_price, exit_price, stoploss_alert_sent, profit_alert_sent, quantity FROM portfolio WHERE user_id=$1 AND symbol=$2 AND status='open'",
        [user.id, symbol]
      );

      const { totalQuantity, avgEntryPrice } = calculateAggregatedPosition(portfolioRes.rows);

      const args = ["../python/engine.py", symbol];
      if (avgEntryPrice) args.push("--entry", avgEntryPrice);

      const result = await runPythonEngine(args);
      if (!result) continue;

      let msgText = `📊 *${result.symbol}* Update\n\n`;
      msgText += `💰 Price: ₹${result.price}`;
      if (avgEntryPrice) msgText += ` (Avg Entry: ₹${avgEntryPrice.toFixed(2)})`;
      if (totalQuantity) msgText += ` | Qty: ${totalQuantity}`;
      msgText += `\n⚡ Recommendation: ${result.recommendation || "Wait / Monitor"}\n`;

      await sendWhatsApp(user.phone, msgText);
      if (result.chart) await sendWhatsAppImage(user.phone, result.chart, `📊 ${result.symbol} Price Chart`);
    }
  }
}

module.exports = { runAlerts, processMessage };
