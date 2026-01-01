const { spawn } = require("child_process");

// ---------------------- Run Python Engine ----------------------
function runPythonEngine(args) {
  return new Promise((resolve, reject) => {
    const py = spawn("python3", args);
    let output = "";

    py.stdout.on("data", (data) => { output += data.toString(); });
    py.stderr.on("data", (err) => console.error("Python error:", err.toString()));

    py.on("close", (code) => {
      if (code === 0) {
        try {
          resolve(JSON.parse(output)); // parse JSON here
        } catch (err) {
          reject(new Error("Python output is not valid JSON"));
        }
      } else reject(new Error("Python script failed"));
    });
  });
}

// ---------------------- Build WhatsApp / PWA Message ----------------------
function buildWhatsAppMessage(result) {
  let msg = `<strong>📊 ${result.symbol} Update</strong><br><br>`;

  // Price & Entry
  if (result.price !== undefined) {
    msg += `💰 Price: ₹${result.price}`;
    if (result.entry_price) msg += ` (Entry: ₹${result.entry_price})`;
    msg += "<br>";
  }

  // P/L & Exit
  if (result.entry_price) {
    const pl = ((result.price - result.entry_price) / result.entry_price) * 100;
    msg += pl >= 0 ? `🟢 P/L: +${pl.toFixed(2)}%<br>` : `🔴 P/L: ${pl.toFixed(2)}%<br>`;

    if (result.exit_price) msg += `🔵 Exit Price: ₹${result.exit_price}<br>`;
    else {
      const suggestedExit = result.entry_price * 0.95;
      msg += `🔴 Suggested Exit (Stop Loss): ₹${suggestedExit.toFixed(2)}<br>`;
    }
  }

  // High / Low
  if (result.low && result.high) {
    msg += `📉 Low / 📈 High: ₹${result.low} / ₹${result.high}<br>`;
  }

  // Volume
  if (result.volume !== undefined && result.avg_volume !== undefined) {
    const volEmoji = result.volume > result.avg_volume ? "📈" : "📉";
    msg += `${volEmoji} Volume: ${result.volume} | Avg: ${result.avg_volume.toFixed(0)}<br>`;
  }

  // Change %
  if (result.change_percent !== undefined) {
    const changeEmoji = result.change_percent > 0 ? "🔺" : (result.change_percent < 0 ? "🔻" : "➖");
    msg += `${changeEmoji} Change: ${result.change_percent.toFixed(2)}%<br>`;
  }

  // Twitter Sentiment
  msg += `🧠 Sentiment: ${result.sentiment_type?.toUpperCase() || "N/A"} (${result.sentiment || 0})<br><br>`;

  // Alerts
  if (!result.alerts || result.alerts.length === 0) {
    msg += `⚠️ No strong signal yet<br>📌 Stock is in watch mode<br>`;
  } else {
    msg += `🚨 Alerts:<br>`;
    result.alerts.forEach(alert => {
      if (alert === "profit") msg += `* 📈 Profit booking zone<br>`;
      if (alert === "loss") msg += `* 📉 Stoploss breached<br>`;
      if (alert === "buy_signal") msg += `* 🟢 Accumulation detected<br>`;
      if (alert === "trap_warning") msg += `* 🚨 Hype trap risk<br>`;
      if (alert === "invalid_symbol") msg += `* ❌ Invalid symbol<br>`;
      if (alert === "error") msg += `* ⚠️ Engine error<br>`;
    });
  }

  // Suggested Entry Zone
  if (result.suggested_entry) {
    msg += `<br>🎯 Suggested Entry: ₹${result.suggested_entry.lower} - ₹${result.suggested_entry.upper}<br>`;
  }

  // Chart
  if (result.chart) {
    msg += `<br><img src="data:image/png;base64,${result.chart}" style="max-width:100%;margin-top:10px;">`;
  }

  return { text: msg, chart: result.chart || null };
}

module.exports = { runPythonEngine, buildWhatsAppMessage };
