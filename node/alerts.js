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

// --- Helper to run Python engine and return JSON ---
// --- Run Python engine ---
// --- Run Python engine ---
async function runPythonEngine(args, phone = null) {
  if (typeof args === "string") args = [args]; // ensure args is array

  return new Promise((resolve) => {
    const proc = spawn("python3", args, { cwd: __dirname });

    let out = "", err = "";
    proc.stdout.on("data", d => out += d);
    proc.stderr.on("data", d => err += d);

    proc.on("close", async () => {
      if (err) console.error(`[ALERTS] Python stderr: ${err}`);
      try {
        const result = JSON.parse(out);

        if (phone) await sendWhatsApp(phone, buildWhatsAppMessage(result));

        resolve(result);
      } catch (e) {
        console.error("[ALERTS] Failed to parse Python output:", e, out);
        if (phone) {
          await sendWhatsApp(phone, "❌ Could not fetch stock data. Please check symbol or try later.");
        }
        resolve(null);
      }
    });
  });
}



async function runAlerts(extraSymbols = []) {
  console.log("[ALERTS] Running alerts...");
  const users = await pool.query("SELECT id, phone FROM users");
  console.log(`[ALERTS] Found ${users.rows.length} users`);

  for (const user of users.rows) {
    console.log(`[ALERTS] Checking user: ${user.phone} (${user.id})`);

    // Get user watchlist
    const watchlistRes = await pool.query(
      "SELECT symbol FROM watchlist WHERE user_id=$1",
      [user.id]
    );
    const watchlist = watchlistRes.rows.map(w => w.symbol.toUpperCase());
    console.log(`[ALERTS] User watchlist: ${watchlist.join(", ")}`);

    // Combine watchlist + extra symbols (like KPIGREEN)
    const allSymbols = [...new Set([...watchlist, ...extraSymbols])];

    for (const symbol of allSymbols) {
      // Fetch portfolio rows for this symbol
      const portfolioRes = await pool.query(
        "SELECT id, entry_price, exit_price, stoploss_alert_sent, profit_alert_sent, quantity FROM portfolio WHERE user_id=$1 AND symbol=$2 AND status='open'",
        [user.id, symbol]
      );

      if (portfolioRes.rows.length > 0) {
        // Aggregate multiple purchases
        const { totalQuantity, avgEntryPrice } = calculateAggregatedPosition(portfolioRes.rows);
        let stoplossAlertSent = portfolioRes.rows.every(r => r.stoploss_alert_sent);
        let profitAlertSent = portfolioRes.rows.every(r => r.profit_alert_sent);

        const args = ["../python/engine.py", symbol];
        if (avgEntryPrice) args.push("--entry", avgEntryPrice);

        const result = await runPythonEngine(args);
        if (!result) continue;

        // --- Existing portfolio message logic ---
        let msg = `📊 *${result.symbol}* Update\n\n`;
        msg += `💰 Price: ₹${result.price}`;
        if (avgEntryPrice) msg += ` (Avg Entry: ₹${avgEntryPrice.toFixed(2)})`;
        msg += ` | Qty: ${totalQuantity}\n`;

        let recommendation = "Hold";

        if (avgEntryPrice) {
          const pnlPercent = ((result.price - avgEntryPrice) / avgEntryPrice) * 100;
          const pnlEmoji = pnlPercent > 0 ? "🟢" : (pnlPercent < 0 ? "🔴" : "➖");
          msg += `${pnlEmoji} P/L: ${pnlPercent.toFixed(2)}%\n`;

          // Stop-loss
          if (pnlPercent <= -LOSS_THRESHOLD && !stoplossAlertSent) {
            const exitPrice = +(avgEntryPrice * (1 - LOSS_THRESHOLD / 100)).toFixed(2);
            msg += `🔴 Stop-loss breached! Suggested Exit: ₹${exitPrice}\n`;
            recommendation = "Sell";

            for (const row of portfolioRes.rows) {
              await pool.query(
                "UPDATE portfolio SET exit_price=$1, stoploss_alert_sent=TRUE, status='closed' WHERE id=$2",
                [exitPrice, row.id]
              );
            }
            stoplossAlertSent = true;
          }

          // Profit check
          if (pnlPercent >= PROFIT_THRESHOLD && !profitAlertSent) {
            const exitPrice = +(avgEntryPrice * (1 + PROFIT_THRESHOLD / 100)).toFixed(2);
            msg += `🟢 Profit target reached! Suggested Exit: ₹${exitPrice}\n`;
            recommendation = "Sell";

            for (const row of portfolioRes.rows) {
              await pool.query(
                "UPDATE portfolio SET exit_price=$1, profit_alert_sent=TRUE, status='closed' WHERE id=$2",
                [exitPrice, row.id]
              );
            }
            profitAlertSent = true;
          }

          // Buy more suggestion
          if (pnlPercent > BUY_DOWN_THRESHOLD && pnlPercent < 0 && result.sentiment_type === "accumulation") {
            recommendation = "Consider Buying More";
            msg += `💡 Minor loss and accumulation detected. Consider adding shares.\n`;
          }
        }

        // High / Low
        if (result.low !== undefined && result.high !== undefined) {
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

        // Sentiment
        let sentimentEmoji = "🧠";
        if (result.sentiment_type === "accumulation") sentimentEmoji = "🟢";
        if (result.sentiment_type === "distribution") sentimentEmoji = "🔴";
        if (result.sentiment_type === "hype") sentimentEmoji = "🚀";
        msg += `${sentimentEmoji} Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "UNKNOWN"} (${result.sentiment ?? 0})\n\n`;

        msg += `⚡ Recommendation: *${recommendation}*\n`;

        // Engine alerts
        if (!result.alerts || result.alerts.length === 0) {
          msg += `⚠️ No strong signal yet\n📌 Stock is in watch mode`;
        } else {
          msg += `🚨 Alerts:\n`;
          for (const alert of result.alerts) {
            if (alert === "profit") msg += `• 📈 Profit booking zone\n`;
            if (alert === "loss") msg += `• 📉 Stoploss breached\n`;
            if (alert === "buy_signal") msg += `• 🟢 Accumulation detected\n`;
            if (alert === "trap_warning") msg += `• 🚨 Hype trap risk\n`;
            if (alert === "invalid_symbol") msg += `• ❌ Invalid symbol\n`;
            if (alert === "error") msg += `• ⚠️ Error fetching data\n`;
          }
        }

        // --- Send WhatsApp messages sequentially ---
        await sendWhatsApp(user.phone, msg);

        if (result.chart) {
          await sendWhatsAppImage(user.phone, result.chart, `📊 ${result.symbol} Price Chart`);
        }

      } else {
        // --- Watchlist-only or extra symbol logic ---
        const args = ["../python/engine.py", symbol];
        console.log(`[ALERTS] Spawning watchlist/extra symbol check: python ${args.join(" ")}`);
        const result = await runPythonEngine(args);
        if (!result) continue;

        let msg = `📊 *${result.symbol}* Update\n\n`;
        msg += `💰 Price: ₹${result.price}\n`;

        if (result.low !== undefined && result.high !== undefined) {
          msg += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}\n`;
        }

        if (result.volume !== undefined && result.avg_volume !== undefined) {
          const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
          msg += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume.toFixed(0)}\n`;
        }

        if (result.change_percent !== undefined) {
          const changeEmoji = result.change_percent > 0 ? "🔺" : (result.change_percent < 0 ? "🔻" : "➖");
          msg += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%\n`;
        }

        let sentimentEmoji = "🧠";
        if (result.sentiment_type === "accumulation") sentimentEmoji = "🟢";
        if (result.sentiment_type === "distribution") sentimentEmoji = "🔴";
        if (result.sentiment_type === "hype") sentimentEmoji = "🚀";
        msg += `${sentimentEmoji} Twitter Sentiment: ${result.sentiment_type?.toUpperCase() || "UNKNOWN"} (${result.sentiment ?? 0})\n\n`;

        let recommendation = "";
        if (result.suggested_entry) {
          const lower = result.suggested_entry.lower;
          const upper = result.suggested_entry.upper;

          if (result.sentiment_type === "accumulation") {
            if (result.price <= upper) {
              recommendation = `Buy now at ₹${result.price} (within entry zone ₹${lower} - ₹${upper})`;
            } else {
              recommendation = `Consider buying if price drops near ₹${lower} - ₹${upper}`;
            }
          } else if (result.sentiment_type === "distribution" || result.sentiment_type === "hype") {
            recommendation = "Not recommended to buy now";
          } else {
            recommendation = `Wait / Monitor. Suggested entry zone: ₹${lower} - ₹${upper}`;
          }
        } else {
          recommendation = "Wait / Monitor";
        }

        msg += `⚡ Recommendation: *${recommendation}*\n`;

        if (!result.alerts || result.alerts.length === 0) {
          msg += `⚠️ No strong signal yet\n📌 Stock is in watch mode`;
        } else {
          msg += `🚨 Alerts:\n`;
          for (const alert of result.alerts) {
            if (alert === "buy_signal") msg += `• 🟢 Accumulation detected\n`;
            if (alert === "trap_warning") msg += `• 🚨 Hype trap risk\n`;
            if (alert === "invalid_symbol") msg += `• ❌ Invalid symbol\n`;
            if (alert === "error") msg += `• ⚠️ Error fetching data\n`;
          }
        }

        await sendWhatsApp(user.phone, msg);

        if (result.chart) {
          await sendWhatsAppImage(user.phone, result.chart, `📊 ${result.symbol} Price Chart`);
        }
      }
    }
  }
}

module.exports = { runAlerts };
