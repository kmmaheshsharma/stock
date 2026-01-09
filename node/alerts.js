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
  if (
    !result ||
    !result.symbol ||
    (Array.isArray(result.alerts) && result.alerts.includes("invalid_symbol"))
  ) {
    console.warn(`[SYMBOL] Invalid or unknown symbol: ${message}`);
    return null; // Node handler will catch this and respond
  }

  console.log(`[SYMBOL] Valid symbol received: ${result.symbol}`);

  // --- Build recommendation string ---
  let recommendation = result.recommendation || "Wait / Monitor";
  if (result.suggested_entry) {
    const lower = result.suggested_entry.lower ?? "N/A";
    const upper = result.suggested_entry.upper ?? "N/A";
    recommendation += ` | Suggested entry: ₹${lower} - ₹${upper}`;
  }

  // --- Build alerts HTML ---
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
  // --- Include Groq AI analysis if available ---
  let groqHTML = "";
  if (result.ai_analysis) {
    const ai = result.ai_analysis;
    const symbol = result.symbol || "";
    const isUS = !symbol.endsWith(".NS") && !symbol.endsWith(".BO");
    const currency = isUS ? "$" : "₹";    
    groqHTML = `<div class="groq-analysis">
      <h4>🤖 AI Analysis</h4>
      <p>📈 Predicted Move: ${ai.predicted_move?.toUpperCase() || "N/A"}</p>
      <p>⚡ Confidence: ${ai.confidence != null ? (ai.confidence * 100).toFixed(2) + "%" : "N/A"}</p>
      <p>🛡️ Support Level: ${currency}${ai.support_level ?? "N/A"}</p>
      <p>⛰️ Resistance Level: ${currency}${ai.resistance_level ?? "N/A"}</p>
      <p>⚠️ Risk: ${ai.risk?.toUpperCase() || "N/A"}</p>
      <p>💡 Recommendation: ${ai.recommendation || "N/A"}</p>
    </div>`;
  }

  // --- Build final HTML message ---
  const msgHTML = `
  <div class="message bot">
    <div class="stock-update">
      <h3>📊 ${result.symbol} Update</h3>
      <p>💰 <strong>Price:</strong> ₹${result.price ?? "Please check the stock symbol, it may be incorrect."}</p>
      <p>📉 Low / 📈 High: ₹${result.low ?? "N/A"} / ₹${result.high ?? "N/A"}</p>
      <p>📊 Volume: ${result.volume ?? "N/A"} | Avg: ${result.avg_volume?.toFixed(0) ?? "N/A"}</p>
      <p>🔻 Change: ${result.change_percent?.toFixed(2) ?? "0"}%</p>
      <p>🧠 Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "NEUTRAL"} (${result.sentiment ?? 0})</p>
      <p>⚡ Recommendation: <strong>${recommendation}</strong></p>
      ${alertsHTML}
      ${groqHTML}
    </div>
  </div>
  `;

  console.log(`[SYMBOL] Response ready for symbol: ${result.symbol}`);
  return {
    text: msgHTML, // HTML content for PWA chat
    chart: result.chart || null
  };
}

// 1️⃣ Get unique symbols with portfolio info
async function getUserSymbols(userId) {
  try {
    // Fetch watchlist
    const watchlistRes = await pool.query(
      "SELECT symbol FROM watchlist WHERE user_id = $1",
      [userId]
    );
    const watchlist = watchlistRes.rows
      .map(r => r.symbol?.trim().toUpperCase())
      .filter(Boolean);

    // Fetch portfolio (open positions)
    const portfolioRes = await pool.query(
      "SELECT symbol, quantity, entry_price FROM portfolio WHERE user_id = $1 AND status = 'open'",
      [userId]
    );
    const portfolio = portfolioRes.rows
      .map(r => ({
        symbol: r.symbol?.trim().toUpperCase(),
        quantity: r.quantity,
        entryPrice: r.entry_price
      }))
      .filter(r => r.symbol);

    // Combine symbols uniquely
    const allSymbolsSet = new Set([...watchlist, ...portfolio.map(p => p.symbol)]);
    const allSymbols = Array.from(allSymbolsSet);

    // Build map for quick lookup of portfolio info
    const portfolioMap = {};
    for (const p of portfolio) {
      portfolioMap[p.symbol] = { quantity: p.quantity, entryPrice: p.entryPrice };
    }

    return { allSymbols, portfolioMap }; // return both
  } catch (err) {
    console.error("Error fetching user symbols:", err);
    return { allSymbols: [], portfolioMap: {} };
  }
}

// 2️⃣ Generate alerts using the combined data
async function generateUserAlerts(user) {
  const { allSymbols, portfolioMap } = await getUserSymbols(user.id);
  const messages = [];

  for (const symbol of allSymbols) {
    const portfolioInfo = portfolioMap[symbol] || null;    
    const totalQuantity = portfolioInfo?.quantity ? Number(portfolioInfo.quantity) : 0;
    const avgEntryPrice = portfolioInfo?.entryPrice ? Number(portfolioInfo.entryPrice) : 0;

    // Prepare Python engine args
    const args = [symbol];
    if (avgEntryPrice) args.push("--entry", avgEntryPrice.toString());

    let result;
    try {
      result = await runPythonEngine(args); // returns JSON from your Python script
    } catch (err) {
      console.error(`Python engine failed for ${symbol}:`, err);
      continue; // skip this symbol if Python fails
    }

    if (!result) continue;

    // Safe fallback values
    const price = result.price != null ? result.price : "Please check the stock symbol, it may be incorrect.";
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

    // Build message
    let msgText = `📊 <b>${symbol}</b> Update<br>`;
    msgText += `💰 Price: ₹${price}`;
    if (totalQuantity > 0) {
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
    const source = totalQuantity > 0 ? "portfolio" : "watchlist";
    if (result.suggested_entry) {
      msgText += `<br>💡 Suggested Entry: ₹${result.suggested_entry.lower} - ₹${result.suggested_entry.upper}`;
    }

    // ================= Grok (AI) Analysis =================
    if (result.ai_analysis) {
      const ai = result.ai_analysis;
      const symbol = result.symbol || "";
      const isUS = !symbol.endsWith(".NS") && !symbol.endsWith(".BO");
      const currency = isUS ? "$" : "₹";          
      msgText += `<br><br>🤖 AI Analysis:`;
      msgText += `<br>📈 Predicted Move: ${ai.predicted_move?.toUpperCase() || "N/A"}`;
      msgText += `<br>⚡ Confidence: ${ai.confidence != null ? (ai.confidence * 100).toFixed(2) + "%" : "N/A"}`;
      msgText += `<br>🛡️ Support Level: ${currency}${ai.support_level ?? "N/A"}`;
      msgText += `<br>⛰️ Resistance Level: ${currency}${ai.resistance_level ?? "N/A"}`;
      msgText += `<br>⚠️ Risk: ${ai.risk?.toUpperCase() || "N/A"}`;
      msgText += `<br>💡 Recommendation: ${ai.recommendation || "N/A"}`;
    }

    messages.push({ text: msgText, chart: result.chart, __raw_result: result || null, source: source });
  }

  return messages;
}

async function getLastKnownState(userId, symbol) {
  const row = await pool.query(`
    SELECT
      last_known_price AS price,
      last_known_change_percent AS change_percent,
      last_known_sentiment AS sentiment
    FROM portfolio
    WHERE user_id = $1 AND symbol = $2
    UNION ALL
    SELECT
      last_known_price,
      last_known_change_percent,
      last_known_sentiment
    FROM watchlist
    WHERE user_id = $1 AND symbol = $2
    LIMIT 1
  `, [userId, symbol]);
  console.log(`[STATE] Last known state for ${symbol}:`, row.rows[0] || null);
  return row.rows[0] || null;
}
function detectMeaningfulChange(result, lastState) {
  const changes = [];
  if (!lastState) {
    changes.push("Initial tracking started");
    return changes;
  }
  if (lastState.change_percent !== null && Math.abs(result.change_percent - lastState.change_percent) >= 1) {
    changes.push(
      `Price ${result.change_percent > 0 ? "↑" : "↓"} ${result.change_percent}%`
    );
  }
  if (lastState.sentiment && result.sentiment && lastState.sentiment !== result.sentiment ) {
    changes.push(`Sentiment → ${result.sentiment}`);
  }
  if (result.alerts?.includes("buy_signal")) {
    changes.push("Buy signal");
  }
  if (result.alerts?.includes("profit")) {
    changes.push("Profit booking zone");
  }
  if (result.alerts?.includes("loss")) {
    changes.push("Stop loss alert");
  }
  return changes;
}
async function saveLastStatus({
  userId,
  symbol,
  price,
  changePercent,
  sentiment,
  summary
}) {
  const isPortfolio = await pool.query(
    `SELECT 1 FROM portfolio WHERE user_id=$1 AND symbol=$2`,
    [userId, symbol]
  );

  const table = isPortfolio.rowCount ? "portfolio" : "watchlist";

  await pool.query(`
    UPDATE ${table}
    SET
      last_known_price = $1,
      last_known_change_percent = $2,
      last_known_sentiment = $3,
      last_update_summary = $4,
      last_update_at = NOW(),
      has_unread_update = TRUE
    WHERE user_id = $5 AND symbol = $6
  `, [
    price,
    changePercent,
    sentiment,
    summary,
    userId,
    symbol
  ]);
}
function extractSymbolFromMessage(text) {
  // Matches: <b>TCS</b>
  const match = text.match(/<b>([^<]+)<\/b>/);
  return match ? match[1].trim() : null;
}

module.exports = { generateUserAlerts, processMessage, getLastKnownState, detectMeaningfulChange, saveLastStatus, extractSymbolFromMessage };
