const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const cardsEl = document.getElementById("sentiment-cards");
const alertsBtn = document.getElementById("alerts-btn");

// Clear previous content on load
messagesEl.innerHTML = "";
cardsEl.innerHTML = "";

// ---------------------- Append chat messages ----------------------
function appendMessage(sender, html, isTyping = false) {
  const div = document.createElement("div");
  div.className = sender === "You" ? "user-msg" : "bot-msg";

  div.innerHTML = `
    <div class="msg-content">${html}</div>
    <div class="msg-time">${isTyping ? "..." : new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
  `;

  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  return div;
}

// ---------------------- Show typing indicator ----------------------
function botTypingIndicator() {
  return appendMessage("Bot", "Bot is typing...", true);
}

// ---------------------- Delay helper ----------------------
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ---------------------- Send chat messages ----------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg) return;

  appendMessage("You", msg);
  input.value = "";

  const typingDiv = botTypingIndicator();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg })
    });
    const data = await res.json();

    // simulate 1–2 second typing delay
    await delay(Math.random() * 1000 + 1000);

    typingDiv.remove();
    appendMessage("Bot", data.text); // display bot message
  } catch (err) {
    typingDiv.remove();
    appendMessage("Bot", "⚠️ Error fetching response");
    console.error(err);
  }
});

// ---------------------- Alerts Button ----------------------
alertsBtn.addEventListener("click", async () => {
  const typingDiv = botTypingIndicator();

  try {
    const res = await fetch("/api/alerts");
    const data = await res.json();

    // simulate 1–2 second typing delay
    await delay(Math.random() * 1000 + 1000);

    typingDiv.remove();

    if (!data || data.length === 0) {
      appendMessage("Bot", "No alerts at the moment 🔔");
      return;
    }

    data.forEach(alert => {
      appendMessage("Bot", `<strong>${alert.symbol}</strong> | ${alert.message}`);
    });
  } catch (err) {
    typingDiv.remove();
    appendMessage("Bot", "⚠️ Failed to fetch alerts");
    console.error(err);
  }
});

// ---------------------- Load sentiment cards ----------------------
async function loadSentiments() {
  try {
    const res = await fetch("/api/sentiments");
    const data = await res.json();

    cardsEl.innerHTML = "";
    data.forEach(stock => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <strong>${stock.symbol}</strong><br>
        Sentiment: <strong style="color:${getColor(stock.sentiment)}">${stock.sentiment}</strong>
        <div class="progress-bar"><div class="indicator" style="left:${stock.percent}%"></div></div>
        ${stock.change} | ${stock.trend}
      `;
      cardsEl.appendChild(card);
    });
  } catch (err) {
    console.error("Failed to load sentiments", err);
  }
}

// ---------------------- Sentiment color ----------------------
function getColor(sentiment) {
  if (sentiment === "Bullish") return "green";
  if (sentiment === "Bearish") return "red";
  return "goldenrod";
}

// ---------------------- Initial load & refresh ----------------------
loadSentiments();
setInterval(loadSentiments, 30000);

// ---------------------- Service Worker ----------------------
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").then(() => console.log("Service Worker registered"));
}
