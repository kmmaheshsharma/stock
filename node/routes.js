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

  if (text.startsWith("buy") || text.includes("purchase")) return "BUY";
  if (text.startsWith("sell") || text.includes("exit")) return "SELL";
  if (text.startsWith("track") || text.includes("add to watchlist")) return "TRACK";
  if (/^[A-Z]{2,15}$/.test(text.toUpperCase())) return "SYMBOL";

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
exports.handleChat = async (req, res) => {
  try {
    const text = req.body.message?.trim();
    if (!text) return res.json({ text: "❌ Empty message" });

    // For PWA use a fixed user or session-based user
    const userId = await getOrCreateUser("PWA_USER");

    // ---------- GREETING ----------
    const greetings = ["hi", "hello", "hey", "hii"];
    if (greetings.includes(text.toLowerCase())) {
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
      return res.json({
        text: welcomeMsg,
        chart: null
      });
    }

    const intent = detectIntent(text);

    // ---------- SWITCH INTENT ----------
    switch (intent) {

      case "SHOW_WATCHLIST": {
        const r = await pool.query(
          "SELECT symbol FROM watchlist WHERE user_id=$1",
          [userId]
        );
        return res.json({
          text: r.rows.length
            ? `📌 Your Watchlist: ${r.rows.map(x => x.symbol).join(", ")}`
            : "📌 Your watchlist is empty",
          chart: null
        });
      }

      case "SHOW_PORTFOLIO": {
        const r = await pool.query(
          "SELECT symbol, quantity, entry_price, exit_price FROM portfolio WHERE user_id=$1",
          [userId]
        );

        if (!r.rows.length)
          return res.json({ text: "📊 Your portfolio is empty", chart: null });

        let msg = "📊 <b>Your Portfolio</b><br><br>";
        r.rows.forEach(row => {
          msg += `${row.symbol}: ${row.quantity} @ ₹${row.entry_price}`;
          if (row.exit_price) msg += ` | Exit ₹${row.exit_price}`;
          msg += "<br>";
        });

        return res.json({ text: msg, chart: null });
      }

      case "TRACK": {
        const symbol = text.split(" ")[1];
        if (!symbol)
          return res.json({ text: "❌ Usage: TRACK SYMBOL", chart: null });

        await pool.query(
          "INSERT INTO watchlist(user_id, symbol) VALUES($1,$2) ON CONFLICT DO NOTHING",
          [userId, symbol.toUpperCase()]
        );

        return res.json({
          text: `✅ ${symbol.toUpperCase()} added to watchlist`,
          chart: null
        });
      }

      case "BUY": {
        const [, symbol, entry, qty] = text.split(" ");
        if (!symbol || !entry || !qty)
          return res.json({
            text: "❌ Usage: BUY SYMBOL ENTRY_PRICE QUANTITY",
            chart: null
          });

        await addToPortfolio(userId, symbol, parseFloat(entry), parseInt(qty));
        return res.json({
          text: `✅ Bought ${qty} shares of ${symbol.toUpperCase()} @ ₹${entry}`,
          chart: null
        });
      }

      case "SELL": {
        const [, symbol, exit] = text.split(" ");
        if (!symbol || !exit)
          return res.json({
            text: "❌ Usage: SELL SYMBOL EXIT_PRICE",
            chart: null
          });

        await pool.query(
          `UPDATE portfolio SET exit_price=$1 
           WHERE user_id=$2 AND symbol=$3 AND exit_price IS NULL`,
          [exit, userId, symbol.toUpperCase()]
        );

        return res.json({
          text: `✅ Exit price set for ${symbol.toUpperCase()} @ ₹${exit}`,
          chart: null
        });
      }

      case "SYMBOL": {
      try
      {
        const symbolQuery = text.toUpperCase();
        const result = await processMessage(symbolQuery);

        if (typeof result === "object" && result.symbol) {
          let msgText = `📊 *${result.symbol}* Update\n\n`;
          msgText += `💰 Price: ₹${result.price}\n`;
          if (result.low && result.high) msgText += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}\n`;
          if (result.volume && result.avg_volume) {
            const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
            msgText += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume.toFixed(0)}\n`;
          }
          if (result.change_percent !== undefined) {
            const changeEmoji = result.change_percent > 0 ? "🔺" : (result.change_percent < 0 ? "🔻" : "➖");
            msgText += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%\n`;
          }

          let sentimentEmoji = "🧠";
          if (result.sentiment_type === "accumulation") sentimentEmoji = "🟢";
          if (result.sentiment_type === "distribution") sentimentEmoji = "🔴";
          if (result.sentiment_type === "hype") sentimentEmoji = "🚀";
          msgText += `${sentimentEmoji} Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "UNKNOWN"} (${result.sentiment ?? 0})\n\n`;

          let recommendation = result.recommendation || "Wait / Monitor";
          if (result.suggested_entry) {
            const lower = result.suggested_entry.lower;
            const upper = result.suggested_entry.upper;
            recommendation += ` | Suggested entry: ₹${lower} - ₹${upper}`;
          }
          msgText += `⚡ Recommendation: *${recommendation}*\n`;

          if (!result.alerts || result.alerts.length === 0) msgText += `⚠️ No strong signal yet\n📌 Stock is in watch mode`;
          else {
            msgText += `🚨 Alerts:\n`;
            for (const alert of result.alerts) {
              if (alert === "buy_signal") msgText += `• 🟢 Accumulation detected\n`;
              if (alert === "trap_warning") msgText += `• 🚨 Hype trap risk\n`;
              if (alert === "invalid_symbol") msgText += `• ❌ Invalid symbol\n`;
              if (alert === "error") msgText += `• ⚠️ Error fetching data\n`;
            }
          }
          return res.json({
            text: msgText,
            chart: result.chart || null
          });
        } else {
            return {
              text: "❌ Unable to fetch stock data",
              chart: null
            };
        }    
      } catch (err) {
          console.error("Error in SYMBOL case:", err);
          return res.json({ text: "❌ Error fetching stock data", chart: null });
        }
      }
    default:
       return res.json({
         text:
           "❌ I didn’t understand.<br><br>" +
           "Try:<br>" +
           "• Show my watchlist<br>" +
           "• Show my portfolio<br>" +
           "• BUY / SELL / TRACK<br>" +
           "• Or send a stock symbol",
         chart: null
       });
    }

  } catch (err) {
    console.error("[handleChat]", err);
    res.status(500).json({ text: "⚠️ Server error", chart: null });
  }
};

// --- Main route handler ---
exports.handleMessage = async (req, res) => {
  const msg = req.body.entry?.[0]?.changes?.[0]?.value?.messages?.[0];
  if (!msg) return res.sendStatus(200);

  const phone = msg.from;
  const text = msg.text?.body?.trim();

  // --- Ignore WhatsApp sandbox test messages ---
  if (text && text.toLowerCase().includes("test")) {
    console.log("Ignored WhatsApp sandbox test message");
    return res.sendStatus(200);
  }

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
      const watchlistRes = await pool.query("SELECT symbol FROM watchlist WHERE user_id=$1", [userId]);
      if (!watchlistRes.rows.length) await sendWhatsApp(phone, "📌 Your watchlist is empty");
      else await sendWhatsApp(phone, `📌 Your Watchlist: ${watchlistRes.rows.map(r => r.symbol).join(", ")}`);
      break;
    }

    case "SHOW_PORTFOLIO": {
      const portfolioRes = await pool.query(
        "SELECT symbol, quantity, entry_price, exit_price FROM portfolio WHERE user_id=$1",
        [userId]
      );
      if (!portfolioRes.rows.length) await sendWhatsApp(phone, "📌 Your portfolio is empty");
      else {
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
        await pool.query("INSERT INTO watchlist(user_id, symbol) VALUES($1,$2)", [userId, symbolTrack.toUpperCase()]);
        await sendWhatsApp(phone, `✅ ${symbolTrack.toUpperCase()} added to watchlist`);
      } else await sendWhatsApp(phone, "❌ Please provide a symbol, e.g. TRACK IFL");
      break;
    }

    case "BUY": {
      const parts = text.split(" ");
      const symbol = parts[1];
      const entryPrice = parseFloat(parts[2]);
      const quantity = parseInt(parts[3], 10);

      if (!symbol || isNaN(entryPrice) || isNaN(quantity)) {
        await sendWhatsApp(phone, "❌ Usage: BUY SYMBOL ENTRY_PRICE QUANTITY");
      } else {
        await addToPortfolio(userId, symbol, entryPrice, quantity);
        await sendWhatsApp(phone, `✅ Added ${quantity} shares of ${symbol.toUpperCase()} at ₹${entryPrice} to your portfolio`);
      }
      break;
    }

    case "SELL": {
      const parts = text.split(" ");
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
        await sendWhatsApp(phone, `✅ Exit price for ${symbol.toUpperCase()} set at ₹${exitPrice}`);
      }
      break;
    }

    case "SYMBOL": {
      const symbolQuery = text.toUpperCase();
      const result = await processMessage(symbolQuery);

      if (typeof result === "object" && result.symbol) {
        let msgText = `📊 *${result.symbol}* Update\n\n`;
        msgText += `💰 Price: ₹${result.price}\n`;
        if (result.low && result.high) msgText += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}\n`;
        if (result.volume && result.avg_volume) {
          const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
          msgText += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume.toFixed(0)}\n`;
        }
        if (result.change_percent !== undefined) {
          const changeEmoji = result.change_percent > 0 ? "🔺" : (result.change_percent < 0 ? "🔻" : "➖");
          msgText += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%\n`;
        }

        let sentimentEmoji = "🧠";
        if (result.sentiment_type === "accumulation") sentimentEmoji = "🟢";
        if (result.sentiment_type === "distribution") sentimentEmoji = "🔴";
        if (result.sentiment_type === "hype") sentimentEmoji = "🚀";
        msgText += `${sentimentEmoji} Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "UNKNOWN"} (${result.sentiment ?? 0})\n\n`;

        let recommendation = result.recommendation || "Wait / Monitor";
        if (result.suggested_entry) {
          const lower = result.suggested_entry.lower;
          const upper = result.suggested_entry.upper;
          recommendation += ` | Suggested entry: ₹${lower} - ₹${upper}`;
        }
        msgText += `⚡ Recommendation: *${recommendation}*\n`;

        if (!result.alerts || result.alerts.length === 0) msgText += `⚠️ No strong signal yet\n📌 Stock is in watch mode`;
        else {
          msgText += `🚨 Alerts:\n`;
          for (const alert of result.alerts) {
            if (alert === "buy_signal") msgText += `• 🟢 Accumulation detected\n`;
            if (alert === "trap_warning") msgText += `• 🚨 Hype trap risk\n`;
            if (alert === "invalid_symbol") msgText += `• ❌ Invalid symbol\n`;
            if (alert === "error") msgText += `• ⚠️ Error fetching data\n`;
          }
        }

        await sendWhatsApp(phone, msgText);

        if (result.chart) {
          await sendWhatsAppImage(phone, result.chart, `📊 ${result.symbol} Price Chart`);
        }

      } else {
        await sendWhatsApp(phone, result || "❌ Could not fetch stock info. Try again later.");
      }
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
