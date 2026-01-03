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

  // --- Early check for invalid symbol ---
  if (!result || !result.symbol || (Array.isArray(result.alerts) && result.alerts.includes("invalid_symbol"))) {
    console.warn(`[SYMBOL] Invalid or unknown symbol: ${message}`);
    return null; // Node handler will catch this and respond
  }

  console.log(`[SYMBOL] Valid symbol received: ${result.symbol}`);

  // --- Build HTML message ---
  let recommendation = result.recommendation || "Wait / Monitor";
  if (result.suggested_entry) {
    const lower = result.suggested_entry.lower ?? "N/A";
    const upper = result.suggested_entry.upper ?? "N/A";
    recommendation += ` | Suggested entry: ₹${lower} - ₹${upper}`;
  }

  let alertsHTML = "";
  if (!Array.isArray(result.alerts) || result.alerts.length === 0) {
    alertsHTML = `<p>⚠️ No strong signal yet<br>📌 Stock is in watch mode</p>`;
  } else {
    alertsHTML = `<p>🚨 Alerts:<br>`;
    for (const alert of result.alerts) {
      if (alert === "profit") alertsHTML += `• 📈 Profit booking zone<br>`;
      if (alert === "loss") alertsHTML += `• 📉 Stoploss breached<br>`;
      if (alert === "buy_signal") alertsHTML += `• 🟢 Accumulation detected<br>`;
      if (alert === "trap_warning") alertsHTML += `• 🚨 Hype trap risk<br>`;
      if (alert === "error") alertsHTML += `• ⚠️ Error fetching data<br>`;
    }
    alertsHTML += `</p>`;
  }

const msgHTML = `
<div class="message bot">
  <div class="stock-update">
    <h3>📊 ${result.symbol} Update</h3>
    <p>💰 <strong>Price:</strong> ₹${result.price ?? "N/A"}</p>
    <p>📉 Low / 📈 High: ₹${result.low ?? "N/A"} / ₹${result.high ?? "N/A"}</p>
    <p>📊 Volume: ${result.volume ?? "N/A"} | Avg: ${result.avg_volume?.toFixed(0) ?? "N/A"}</p>
    <p>🔻 Change: ${result.change_percent?.toFixed(2) ?? "0"}%</p>
    <p>🧠 Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "NEUTRAL"} (${result.sentiment ?? 0})</p>
    <p>⚡ Recommendation: <strong>${recommendation}</strong></p>
    ${alertsHTML ?? ""}
  </div>
</div>
`;

  console.log(`[SYMBOL] Response ready for symbol: ${result.symbol}`);
  return {
    text: msgHTML, // HTML content for PWA chat
    chart: result.chart || null
  };
}

async function getUserSymbols(userId) {
  // 1️⃣ Get watchlist symbols
  const watchlistRes = await pool.query(
    "SELECT symbol FROM watchlist WHERE user_id = $1",
    [userId]
  );
  const watchlist = watchlistRes.rows.map(r => r.symbol.toUpperCase());

  // 2️⃣ Get portfolio symbols (only open positions)
  const portfolioRes = await pool.query(
    "SELECT symbol FROM portfolio WHERE user_id = $1 AND status = 'open'",
    [userId]
  );
  const portfolio = portfolioRes.rows.map(r => r.symbol.toUpperCase());

  // 3️⃣ Combine and remove duplicates
  const allSymbols = [...new Set([...watchlist, ...portfolio])];

  return allSymbols;
}

async function generateUserAlerts(user) {
  const symbols = await getUserSymbols(user.id); // portfolio + watchlist symbols
  const messages = [];
  const uniqueSymbols = [...new Set(symbols)];  // remove duplicates
  for (const symbol of uniqueSymbols) {
    // Get portfolio info
    const portfolioRes = await pool.query(
      `SELECT id, entry_price, exit_price, quantity
       FROM portfolio
       WHERE user_id = $1 AND symbol = $2 AND status = 'open'`,
      [user.id, symbol]
    );

    const { totalQuantity, avgEntryPrice } = calculateAggregatedPosition(portfolioRes.rows);

    // Run Python engine
    const args = [symbol];
    if (avgEntryPrice) args.push("--entry", avgEntryPrice.toString());

    let result;
    try {
      result = await runPythonEngine(args); // returns full JSON from your Python script
    } catch (err) {
      console.error(`Python engine failed for ${symbol}:`, err);
      continue; // skip this symbol if Python fails
    }

    if (!result) continue;

    // Safe fallback values
    const price = result.price != null ? result.price : "N/A";
    const low = result.low != null ? result.low : "N/A";
    const high = result.high != null ? result.high : "N/A";
    const volume = result.volume != null ? result.volume : "N/A";
    const avgVolume = result.avg_volume != null ? result.avg_volume : "N/A";
    const change = result.change_percent != null ? result.change_percent : "N/A";
    const sentiment = result.sentiment || "NEUTRAL";
    const sType = result.sentiment_type || "neutral";
    const recommendation = result.alerts.includes("buy_signal")
      ? "Buy"
      : result.alerts.includes("profit")
      ? "Take Profit"
      : result.alerts.includes("loss")
      ? "Cut Loss"
      : "Wait / Monitor";

    // Construct message
    let msgText = `📊 <b>${symbol}</b> Update<br>`;
    msgText += `💰 Price: ₹${price}`;

    if (totalQuantity) {
      msgText += ` (Avg Entry: ₹${avgEntryPrice.toFixed(2)}) | Qty: ${totalQuantity}`;
      msgText += `<br>📌 Stock is in portfolio`;
    } else {
      msgText += `<br>📌 Stock is in watch mode`;
    }

    msgText += `<br>📉 Low / 📈 High: ₹${low} / ₹${high}`;
    msgText += `<br>📊 Volume: ${volume} | Avg: ${avgVolume}`;
    msgText += `<br>🔻 Change: ${change}%`;
    msgText += `<br>🧠 Twitter Sentiment: ${sentiment} (${sType})`;
    msgText += `<br>⚡ Recommendation: ${recommendation}`;

    if (result.suggested_entry) {
      msgText += `<br>💡 Suggested Entry: ₹${result.suggested_entry.lower} - ₹${result.suggested_entry.upper}`;
    }

    // Include chart if available
    messages.push({ text: msgText, chart: result.chart || null });
  }

  return messages;
}

// ---------------------- Helper ----------------------
function calculateAggregatedPosition(rows) {
  if (!rows || rows.length === 0) return { totalQuantity: 0, avgEntryPrice: 0 };

  let totalQuantity = 0;
  let totalCost = 0;

  for (const row of rows) {
    totalQuantity += row.quantity;
    totalCost += row.entry_price * row.quantity;
  }

  const avgEntryPrice = totalQuantity > 0 ? totalCost / totalQuantity : 0;

  return { totalQuantity, avgEntryPrice };
}


module.exports = { generateUserAlerts, processMessage };
