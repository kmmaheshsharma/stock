const { sendWhatsApp, sendWhatsAppImage } = require("./whatsapp");
const { pool } = require("./db");
const fs = require("fs");
const path = require("path");
const { processMessage } = require("./alerts"); // <-- import processMessage

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
  const text = msg.text?.body?.trim();

  const userId = await getOrCreateUser(phone);

  // --- Handle greetings directly ---
  const greetings = ["hi", "hello", "hey", "hii"];
  if (!text || greetings.includes(text.toLowerCase())) {
    const welcomeMsg =
      "🌟👋 *Welcome to StockBot!* 👋🌟\n\n" +
      "💹 Track your stocks, manage your portfolio, and get smart recommendations in real-time.\n\n" +
      "📚 *Commands you can use:*\n" +
      "• 📌 Show my *watchlist* (example: type `Show my watchlist`)\n" +
      "• 📊 Show my *portfolio* (example: type `Show my portfolio`)\n" +
      "• ➕ Track a stock: *TRACK SYMBOL* (example: `TRACK IFL`)\n" +
      "• 💰 Buy: *BUY SYMBOL ENTRY_PRICE QUANTITY* (example: `BUY IFL 1574 10`)\n" +
      "• 📉 Sell: *SELL SYMBOL EXIT_PRICE* (example: `SELL IFL 1600`)\n" +
      "• 🔎 Or just send a stock symbol like *IFL* or *KPIGREEN* to get instant updates";
    await sendWhatsApp(phone, welcomeMsg);
    return res.sendStatus(200);
  }

  const intent = detectIntent(text);

  switch(intent) {
    case "SHOW_WATCHLIST": {
      const watchlistRes = await pool.query(
        "SELECT symbol FROM watchlist WHERE user_id=$1",
        [userId]
      );
      if (!watchlistRes.rows.length) {
        await sendWhatsApp(phone, "📌 Your watchlist is empty");
      } else {
        const symbols = watchlistRes.rows.map(r => r.symbol).join(", ");
        await sendWhatsApp(phone, `📌 Your Watchlist: ${symbols}`);
      }
      break;
    }

    case "SHOW_PORTFOLIO": {
      const portfolioRes = await pool.query(
        "SELECT symbol, quantity, entry_price, exit_price FROM portfolio WHERE user_id=$1",
        [userId]
      );
      if (!portfolioRes.rows.length) {
        await sendWhatsApp(phone, "📌 Your portfolio is empty");
      } else {
        let msgText = "📊 Your Portfolio:\n\n";
        portfolioRes.rows.forEach(r => {
          msgText += `${r.symbol}: ${r.quantity} shares @ ₹${r.entry_price}`;
          if (r.exit_price) msgText += ` | Exit: ₹${r.exit_price}`;
          msgText += "\n";
        });
        await sendWhatsApp(phone, msgText);
      }
      break;
    }

    case "TRACK": {
      const symbolTrack = text.split(" ")[1];
      if (symbolTrack) {
        await pool.query(
          "INSERT INTO watchlist(user_id, symbol) VALUES($1,$2)",
          [userId, symbolTrack.toUpperCase()]
        );
        await sendWhatsApp(phone, `✅ ${symbolTrack.toUpperCase()} added to watchlist`);
      } else {
        await sendWhatsApp(phone, "❌ Please provide a symbol, e.g. TRACK IFL");
      }
      break;
    }

    case "BUY": {
      const parts = text.split(" "); // BUY SYMBOL ENTRY_PRICE QUANTITY
      const symbol = parts[1];
      const entryPrice = parseFloat(parts[2]);
      const quantity = parseInt(parts[3], 10);

      if (!symbol || isNaN(entryPrice) || isNaN(quantity)) {
        await sendWhatsApp(phone, "❌ Usage: BUY SYMBOL ENTRY_PRICE QUANTITY");
      } else {
        await addToPortfolio(userId, symbol, entryPrice, quantity);
        await sendWhatsApp(
          phone,
          `✅ Added ${quantity} shares of ${symbol.toUpperCase()} at ₹${entryPrice} to your portfolio`
        );
      }
      break;
    }

    case "SELL": {
      const parts = text.split(" "); // SELL SYMBOL EXIT_PRICE
      const symbol = parts[1];
      const exitPrice = parseFloat(parts[2]);

      if (!symbol || isNaN(exitPrice)) {
        await sendWhatsApp(phone, "❌ Usage: SELL SYMBOL EXIT_PRICE");
      } else {
        await pool.query(
          `UPDATE portfolio 
           SET exit_price=$1 
           WHERE user_id=$2 AND symbol=$3 AND exit_price IS NULL`,
          [exitPrice, userId, symbol.toUpperCase()]
        );
        await sendWhatsApp(
          phone,
          `✅ Exit price for ${symbol.toUpperCase()} set at ₹${exitPrice}`
        );
      }
      break;
    }

    case "SYMBOL": {
      const symbolQuery = text.toUpperCase();
      // Use processMessage from alerts.js to safely get Python response
      const reply = await processMessage(symbolQuery);
      await sendWhatsApp(phone, reply);
      break;
    }

    default:
      await sendWhatsApp(phone, 
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
