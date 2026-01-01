const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const cardsEl = document.getElementById("sentiment-cards");

// Send chat messages
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg) return;

  appendMessage("You", msg);
  input.value = "";

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: msg })
  });
  const data = await res.json();
  appendMessage("Bot", data.reply);
});

function appendMessage(sender, text) {
  const div = document.createElement("div");
  div.className = sender === "You" ? "user-msg" : "bot-msg";
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Load sentiment cards
async function loadSentiments() {
  const res = await fetch("/api/sentiments");
  const data = await res.json();

  cardsEl.innerHTML = "";
  data.forEach(stock => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <strong>${stock.symbol}</strong> <br>
      Sentiment: <strong style="color:${getColor(stock.sentiment)}">${stock.sentiment}</strong>
      <div class="progress-bar"><div class="indicator" style="left:${stock.percent}%"></div></div>
      ${stock.change} | ${stock.trend}
    `;
    cardsEl.appendChild(card);
  });
}

function getColor(sentiment) {
  if (sentiment === "Bullish") return "green";
  if (sentiment === "Bearish") return "red";
  return "goldenrod";
}

// Initial load + refresh
loadSentiments();
setInterval(loadSentiments, 30000);

// Register service worker
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").then(() => console.log("SW registered"));
}
