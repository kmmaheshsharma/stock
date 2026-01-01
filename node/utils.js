// utils.js
const { spawn } = require("child_process");

function runPythonEngine(message) {
  return new Promise((resolve, reject) => {
    const py = spawn("python3", ["./python/engine.py", message]);
    let output = "";
    py.stdout.on("data", (data) => (output += data.toString()));
    py.stderr.on("data", (err) => console.error("Python error:", err.toString()));
    py.on("close", (code) => {
      if (code === 0) resolve(output.trim());
      else reject(new Error("Python script failed"));
    });
  });
}

function buildWhatsAppMessage(result) {
  let msg = `📊 ${result.symbol} Update\n\n`;
  msg += `💰 Price: ₹${result.price}\n`;
  if (result.entry_price) msg += ` (Entry: ₹${result.entry_price})\n`;
  return msg;
}

module.exports = { runPythonEngine, buildWhatsAppMessage };
