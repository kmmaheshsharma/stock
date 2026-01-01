// utils.js
const { spawn } = require("child_process");

// ---------------------- RUN PYTHON ENGINE ----------------------
function runPythonEngine(args) {
  return new Promise((resolve, reject) => {
    const py = spawn("python3", args);
    let output = "";

    py.stdout.on("data", (data) => {
      output += data.toString();
    });

    py.stderr.on("data", (err) => {
      console.error("Python error:", err.toString());
    });

    py.on("close", (code) => {
      if (code === 0) {
        try {
          resolve(JSON.parse(output)); // parse JSON output
        } catch (err) {
          console.error("Raw Python output:", output);
          reject(new Error("Python output is not valid JSON"));
        }
      } else {
        reject(new Error("Python script failed with code " + code));
      }
    });
  });
}

// ---------------------- BUILD WHATSAPP MESSAGE ----------------------
function buildWhatsAppMessage(result) {
  if (!result) return "⚠️ No data received from engine.";

  let msg = `📊 *${result.symbol || "N/A"}* Update\n\n`;

  if (result.error) {
    msg += `❌ Error: ${result.error}\n`;
    return msg;
  }

  // Price & entry
  msg += `💰 Price: ₹${result.price ?? "N/A"}`;
  if (result.entry_price) msg += ` (Entry: ₹${result.entry_price})`;
  msg += "\n";

  // P/L and suggested exit
  if (result.entry_price && result.price !== undefined) {
    const pnl = ((result.price - result.entry_price) / result.entry_price) * 100;
    const emoji = pnl > 0 ? "🟢" : pnl < 0 ? "🔴" : "➖";
    msg += `${emoji} P/L: ${pnl.toFixed(2)}%\n`;

    if (result.exit_price) msg += `🔵 Exit Price: ₹${result.exit_price}\n`;
  }

  // Low / High
  if (result.low !== undefined && result.high !== undefined) {
    msg += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}\n`;
  }

  // Volume
  if (result.volume !== undefined && result.avg_volume !== undefined) {
    const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
    msg += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume}\n`;
  }

  // Change %
  if (result.change_percent !== undefined) {
    const changeEmoji = result.change_percent > 0 ? "🔺" : result.change_percent < 0 ? "🔻" : "➖";
    msg += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%\n`;
  }

  // Sentiment
  if (result.sentiment_type) {
    let sentimentEmoji = "🧠";
    if (result.sentiment_type === "accumulation") sentimentEmoji = "🟢";
    else if (result.sentiment_type === "distribution") sentimentEmoji = "🔴";
    else if (result.sentiment_type === "hype") sentimentEmoji = "🚀";

    msg += `${sentimentEmoji} Twitter Sentiment: ${result.sentiment_type.toUpperCase()} (${result.sentiment ?? 0})\n`;
  }

  // Suggested entry zone
  if (result.suggested_entry) {
    msg += `📌 Suggested Entry Zone: ₹${result.suggested_entry.lower} - ₹${result.suggested_entry.upper}\n`;
  }

  // Alerts
  if (result.alerts && result.alerts.length > 0) {
    msg += `🚨 Alerts:\n`;
    result.alerts.forEach((alert) => {
      if (alert === "profit") msg += "• 📈 Profit booking zone\n";
      else if (alert === "loss") msg += "• 📉 Stoploss breached\n";
      else if (alert === "buy_signal") msg += "• 🟢 Accumulation detected\n";
      else if (alert === "trap_warning") msg += "• 🚨 Hype trap risk\n";
      else if (alert === "invalid_symbol") msg += "• ❌ Invalid symbol\n";
      else if (alert === "error") msg += "• ⚠️ Error fetching data\n";
    });
  } else {
    msg += "⚠️ No strong signal yet\n📌 Stock is in watch mode\n";
  }

  // Chart link
  if (result.chart) {
    msg += `📊 Chart available\n`; // could also send as image via sendWhatsAppImage
  }

  return msg;
}

module.exports = { runPythonEngine, buildWhatsAppMessage };
