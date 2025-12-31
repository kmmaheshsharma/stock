const { sendWhatsApp, sendWhatsAppImage } = require("./whatsapp");
const { pool } = require("./db");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

// --- Ensure chart folder exists ---
const chartDir = path.join(__dirname, "chart");
if (!fs.existsSync(chartDir)) {
  fs.mkdirSync(chartDir);
}

// --- Helper to get or create user by phone ---
async function getOrCreateUser(phone) {
  const res = await pool.query("SELECT id FROM users WHERE phone=$1", [phone]);
  if (res.rows.length) return res.rows[0].id;
  const insert = await pool.query(
    "INSERT INTO users (phone) VALUES ($1) RETURNING id",
    [phone]
  );
  return insert.rows[0].id;
}

// --- Detect natural language intent ---
function detectIntent(text) {
  text = text.toLowerCase();

  if (text.includes("watchlist") || text.includes("my watchlist") || text.includes("show watchlist")) {
    return "SHOW_WATCHLIST";
  }

  if (text.includes("portfolio") || text.includes("my portfolio") || text.includes("show portfolio")) {
    return "SHOW_PORTFOLIO";
  }

  if (text.startsWith("buy") || text.includes("purchase")) {
    return "BUY";
  }

  if (text.startsWith("sell") || text.includes("exit")) {
    return "SELL";
  }

  if (text.startsWith("track") || text.includes("add to watchlist")) {
    return "TRACK";
  }

  if (/^[A-Z]{2,15}$/.test(text.toUpperCase())) {
    return "SYMBOL";
  }

  return "UNKNOWN";
}

// --- Build WhatsApp message from Python engine result ---
function buildWhatsAppMessage(result) {
  let msg = `📊 ${result.symbol} Update\n\n`;

  // Price & Entry
  msg += `💰 Price: ₹${result.price}`;
  if (result.entry_price) msg += ` (Entry: ₹${result.entry_price})`;
  msg += `\n`;

  // P/L and Suggested Exit (Stop Loss)
  if (result.entry_price) {
    const pl = ((result.price - result.entry_price) / result.entry_price) * 100;
    msg += pl >= 0 ? `🟢 P/L: +${pl.toFixed(2)}%\n` : `🔴 P/L: ${pl.toFixed(2)}%\n`;

    if (result.exit_price) {
      msg += `🔵 Exit Price: ₹${result.exit_price}\n`;
    } else {
      const suggestedExit = result.entry_price * 0.95;
      msg += `🔴 Suggested Exit (Stop Loss): ₹${suggestedExit.toFixed(2)}\n`;
    }
  }

  // High / Low
  if (result.low && result.high) {
    msg += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}\n`;
  }

  // Volume & Avg Volume
  if (result.volume !== undefined && result.avg_volume !== undefined) {
    const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
    msg += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume.toFixed(0)}\n`;
  }

  // Change %
  if (result.change_percent !== undefined) {
    const changeEmoji = result.change_percent > 0 ? "🔺" : (result.change_percent < 0 ? "🔻" : "➖");
    msg += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%\n`;
  }

  // Twitter Sentiment
  msg += `🧠 Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "N/A"} (${result.sentiment || 0})\n\n`;

  // Alerts
  if (!result.alerts || result.alerts.length === 0) {
    msg += `⚠️ No strong signal yet\n📌 Stock is in watch mode`;
  } else {
    msg += `🚨 Alerts:\n`;
    result.alerts.forEach(alert => {
      if (alert === "profit") msg += `* 📈 Profit booking zone\n`;
      if (alert === "loss") msg += `* 📉 Stoploss breached\n`;
      if (alert === "buy_signal") msg += `* 🟢 Accumulation detected\n`;
      if (alert === "trap_warning") msg += `* 🚨 Hype trap risk\n`;
      if (alert === "invalid_symbol") msg += `* ❌ Invalid symbol\n`;
    });
  }

  return msg;
}

// --- Run Python engine ---
async function runPythonEngine(args, phone = null) {
  if (typeof args === "string") args = [args]; // ensure args is array

  return new Promise((resolve) => {
    const proc = spawn("python3", args, { cwd: __dirname });

    let out = "", err = "";
    proc.stdout.on("data", d => out += d);
    proc.stderr.on("data", d => err += d);

    proc.on("close", async () => {
      if (err) console.error(err); // keep only critical errors
      try {
        const result = JSON.parse(out);

        if (phone) await sendWhatsApp(phone, buildWhatsAppMessage(result));

        resolve(result);
      } catch (e) {
        console.error("Failed to parse Python output:", e, out);
        if (phone) {
          await sendWhatsApp(phone, "❌ Could not fetch stock data. Please check symbol or try later.");
        }
        resolve(null);
      }
    });
  });
}

// --- Add stock to portfolio ---
async function addToPortfolio(userId, symbol, entryPrice, quantity) {
  try {
    const res = await pool.query(
      `INSERT INTO portfolio (user_id, symbol, entry_price, quantity)
       VALUES ($1, $2, $3, $4)
       RETURNING *`,
      [userId, symbol.toUpperCase(), entryPrice, quantity]
    );
    return res.rows[0];
  } catch (err) {
    console.error("Failed to add portfolio entry:", err);
    throw err;
  }
}

// --- Main route handler ---
exports.handleMessage = async (req, res) => {
  const msg = req.body.entry?.[0]?.changes?.[0]?.value?.messages?.[0];
  if (!msg) return res.sendStatus(200);

  const phone = msg.from;
  const text = msg.text?.body?.toUpperCase();

  const userId = await getOrCreateUser(phone);

  // --- Welcome / first-time instruction ---
  if (!text || text === "HI" || text === "HELLO") {
    await sendWhatsApp(phone,
      "🌟👋 *Welcome to StockBot!* 👋🌟\n\n" +
      "💹 Track your stocks, manage your portfolio, and get smart recommendations in real-time.\n\n" +
      "📚 *Commands you can use:*\n" +
      "• 📌 Show my *watchlist* (example: type `Show my watchlist`)\n" +
      "• 📊 Show my *portfolio* (example: type `Show my portfolio`)\n" +
      "• ➕ Track a stock: *TRACK SYMBOL* (example: `TRACK IFL`)\n" +
      "• 💰 Buy: *BUY SYMBOL ENTRY_PRICE QUANTITY* (example: `BUY IFL 1574 10`)\n" +
      "• 📉 Sell: *SELL SYMBOL EXIT_PRICE* (example: `SELL IFL 1600`)\n" +
      "• 🔎 Or just send a stock symbol like *IFL* or *KPIGREEN* to get instant updates"
    );
    return res.sendStatus(200);
  }

  const intent = detectIntent(text);

  switch(intent) {
    case "SHOW_WATCHLIST":
      {
        const watchlistRes = await pool.query(
          "SELECT symbol FROM watchlist WHERE user_id=$1",
          [userId]
        );
        if (!watchlistRes.rows.length) {
          sendWhatsApp(phone, "📌 Your watchlist is empty");
        } else {
          const symbols = watchlistRes.rows.map(r => r.symbol).join(", ");
          sendWhatsApp(phone, `📌 Your Watchlist: ${symbols}`);
        }
      }
      break;

    case "SHOW_PORTFOLIO":
      {
        const portfolioRes = await pool.query(
          "SELECT symbol, quantity, entry_price, exit_price FROM portfolio WHERE user_id=$1",
          [userId]
        );
        if (!portfolioRes.rows.length) {
          sendWhatsApp(phone, "📌 Your portfolio is empty");
        } else {
          let msgText = "📊 Your Portfolio:\n\n";
          portfolioRes.rows.forEach(r => {
            msgText += `${r.symbol}: ${r.quantity} shares @ ₹${r.entry_price}`;
            if (r.exit_price) msgText += ` | Exit: ₹${r.exit_price}`;
            msgText += "\n";
          });
          sendWhatsApp(phone, msgText);
        }
      }
      break;

    case "TRACK":
      {
        const symbolTrack = text.split(" ")[1];
        if (symbolTrack) {
          await pool.query(
            "INSERT INTO watchlist(user_id, symbol) VALUES($1,$2)",
            [userId, symbolTrack.toUpperCase()]
          );
          sendWhatsApp(phone, `✅ ${symbolTrack.toUpperCase()} added to watchlist`);
        } else {
          sendWhatsApp(phone, "❌ Please provide a symbol, e.g. TRACK IFL");
        }
      }
      break;

    case "BUY":
      {
        const parts = text.split(" "); // BUY SYMBOL ENTRY_PRICE QUANTITY
        const symbol = parts[1];
        const entryPrice = parseFloat(parts[2]);
        const quantity = parseInt(parts[3], 10);

        if (!symbol || isNaN(entryPrice) || isNaN(quantity)) {
          sendWhatsApp(phone, "❌ Usage: BUY SYMBOL ENTRY_PRICE QUANTITY");
        } else {
          await addToPortfolio(userId, symbol, entryPrice, quantity);
          sendWhatsApp(
            phone,
            `✅ Added ${quantity} shares of ${symbol} at ₹${entryPrice} to your portfolio`
          );
        }
      }
      break;

    case "SELL":
      {
        const parts = text.split(" "); // SELL SYMBOL EXIT_PRICE
        const symbol = parts[1];
        const exitPrice = parseFloat(parts[2]);

        if (!symbol || isNaN(exitPrice)) {
          sendWhatsApp(phone, "❌ Usage: SELL SYMBOL EXIT_PRICE");
        } else {
          await pool.query(
            `UPDATE portfolio 
             SET exit_price=$1 
             WHERE user_id=$2 AND symbol=$3 AND exit_price IS NULL`,
            [exitPrice, userId, symbol.toUpperCase()]
          );
          sendWhatsApp(
            phone,
            `✅ Exit price for ${symbol.toUpperCase()} set at ₹${exitPrice}`
          );
        }
      }
      break;

    case "SYMBOL":
      {
        const symbolQuery = text.toUpperCase();
        const symbolCheck = await pool.query(
          "SELECT 1 FROM watchlist WHERE user_id=$1 AND symbol=$2 UNION SELECT 1 FROM portfolio WHERE user_id=$1 AND symbol=$2",
          [userId, symbolQuery]
        );

        if (symbolCheck.rows.length) {
          await runPythonEngine(["../python/engine.py", symbolQuery], phone);
        } else {
          await sendWhatsApp(phone,
            `❌ I could not find any data for "${symbolQuery}".\n` +
            `• You can add it to your watchlist: TRACK ${symbolQuery}\n` +
            `• Or check your portfolio / watchlist by typing:\n` +
            `  - Show my portfolio\n  - Show my watchlist`
          );
        }
      }
      break;

    default:
      sendWhatsApp(phone, 
        "❌ Sorry, I did not understand. You can ask:\n" +
        "• Show my watchlist\n" +
        "• Show my portfolio\n" +
        "• Buy SYMBOL ENTRY_PRICE QUANTITY\n" +
        "• Sell SYMBOL EXIT_PRICE\n" +
        "• Track SYMBOL\n" +
        "• Or just send a stock symbol like IFL or KPIGREEN"
      );
      break;
  }

  res.sendStatus(200);
};
