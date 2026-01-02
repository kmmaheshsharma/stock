// ---------------------- Elements ----------------------
const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const cardsEl = document.getElementById("sentiment-cards");
const alertsBtn = document.getElementById("alerts-btn");

const signupScreen = document.getElementById("signup-screen");
const chatScreen = document.getElementById("chat-screen");
const signupForm = document.getElementById("signup-form");
const subscribeBtn = document.getElementById("subscribe-btn");
const unsubscribeBtn = document.getElementById("unsubscribe-btn");
const signinBtn = document.getElementById("signin-btn");
const signupBtn = document.getElementById("signup-btn");
// Clear previous content
messagesEl.innerHTML = "";
cardsEl.innerHTML = "";

// ---------------------- Signup Flow ----------------------
// ---------------------- Check Local Storage for User ----------------------
  const phone = localStorage.getItem("userPhone");
  if (phone) {
    // If phone exists, try to fetch user data from the backend
    fetch(`/api/check-user/${phone}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.userId) {
          // User found in the backend, log them in
          localStorage.setItem("userId", data.userId);
          localStorage.setItem("userPhone", phone);
          signupScreen.style.display = "none";
          chatScreen.style.display = "";
          initChatBot(data.userId);
        } else {
          // User not found in the backend, show sign-up screen
          signupScreen.style.display = "";
          chatScreen.style.display = "none";
        }
      })
      .catch((err) => {
        console.error("Error checking user", err);
        signupScreen.style.display = "";
        chatScreen.style.display = "none";
      });
  } else {
    // No phone, show sign-up screen
    signupScreen.style.display = "";
    chatScreen.style.display = "none";
  }
// ---------------------- Handle Sign Up ----------------------
signupBtn.addEventListener("click", async (e) => {
  e.preventDefault();

  const name = document.getElementById("name").value.trim();
  const phone = document.getElementById("phone").value.trim();
  const email = document.getElementById("email").value.trim();
  const subscribed = document.getElementById("subscribe").checked;

  try {
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, phone, email, subscribed })
    });
    const data = await res.json();

    // Store user details in localStorage
    localStorage.setItem("userId", data.userId);
    localStorage.setItem("userPhone", phone);

    // Switch to chat screen
    signupScreen.style.display = "none";
    chatScreen.style.display = "";
    initChatBot(data.userId);
  } catch (err) {
    console.error("Signup failed", err);
    alert("Failed to sign up. Try again.");
  }
});

// ---------------------- Handle Sign In ----------------------
signinBtn.addEventListener("click", async (e) => {
  e.preventDefault();

  const phone = document.getElementById("phone").value.trim();

  if (!phone) {
    alert("Please enter your phone number.");
    return;
  }

  try {
    const res = await fetch(`/api/check-user/${phone}`);
    const data = await res.json();

    if (data.userId) {
      // Store user details in localStorage
      localStorage.setItem("userId", data.userId);
      localStorage.setItem("userPhone", phone);

      // Switch to chat screen
      signupScreen.style.display = "none";
      chatScreen.style.display = "";
      initChatBot(data.userId);
    } else {
      alert("User not found. Please sign up.");
    }
  } catch (err) {
    console.error("Sign in failed", err);
    alert("Failed to sign in. Try again.");
  }
});
// ---------------------- Subscribe / Unsubscribe ----------------------
subscribeBtn.addEventListener("click", async () => {
  const phone = localStorage.getItem("userPhone"); // store phone on signup
  if (!phone) {
    alert("Phone number not found. Please signup again.");
    return;
  }

  const typingDiv = botTypingIndicator();
  try {
    const res = await fetch("/api/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone })
    });
    const data = await res.json();
    await delay(Math.random() * 500 + 500);
    typingDiv.remove();
    appendMessage("Bot", data.message || "Subscribed successfully 🔔");
  } catch (err) {
    typingDiv.remove();
    appendMessage("Bot", "⚠️ Failed to subscribe");
    console.error(err);
  }
});

unsubscribeBtn.addEventListener("click", async () => {
  const phone = localStorage.getItem("userPhone");
  if (!phone) {
    alert("Phone number not found. Please signup again.");
    return;
  }

  const typingDiv = botTypingIndicator();
  try {
    const res = await fetch("/api/unsubscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone })
    });
    const data = await res.json();
    await delay(Math.random() * 500 + 500);
    typingDiv.remove();
    appendMessage("Bot", data.message || "Unsubscribed successfully 🔕");
  } catch (err) {
    typingDiv.remove();
    appendMessage("Bot", "⚠️ Failed to unsubscribe");
    console.error(err);
  }
});
signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("name").value.trim();
  const phone = document.getElementById("phone").value.trim();
  const email = document.getElementById("email").value.trim();
  const subscribed = document.getElementById("subscribe").checked;

  try {
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, phone, email, subscribed })
    });
    const data = await res.json();

    localStorage.setItem("userId", data.userId);
    localStorage.setItem("userPhone", phone); // <-- store phone for later subscribe/unsubscribe

    signupScreen.style.display = "none";
    chatScreen.style.display = "";
    initChatBot(data.userId);

  } catch (err) {
    console.error("Signup failed", err);
    alert("Failed to sign up. Try again.");
  }
});


function initChatBot(userId) {
  console.log("Chat initialized for user", userId);
  loadSentiments();
  setInterval(loadSentiments, 30000);
}

// ---------------------- Chat Functions ----------------------
function appendMessage(sender, html) {
  const div = document.createElement("div");
  div.className = sender === "You" ? "user-msg" : "bot-msg";
  div.innerHTML = `
    <div class="msg-content">${html}</div>
    <div class="msg-time">${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
  `;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function botTypingIndicator() {
  const div = document.createElement("div");
  div.className = "bot-msg";
  div.innerHTML = `<div class="msg-content"><div class="typing"><span></span><span></span><span></span></div></div>`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ---------------------- Handle web chat ----------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  signupScreen.style.display = "none";
  chatScreen.style.display = "";
  const msg = input.value.trim();
  if (!msg) return;

  appendMessage("You", msg);
  input.value = "";

  const typingDiv = botTypingIndicator();
  try {
    const res = await fetch("/api/webchat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg })
    });
    const data = await res.json();

    await delay(Math.random() * 1000 + 1000);
    typingDiv.remove();
    appendMessage("Bot", data.text);
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
    await delay(Math.random() * 1000 + 1000);
    typingDiv.remove();

    if (!data || data.length === 0) {
      appendMessage("Bot", "No alerts at the moment 🔔");
      return;
    }

    data.forEach(alert => {
      appendMessage("Bot", `🚨 ${alert.symbol}: ${alert.message}`);
    });
  } catch (err) {
    typingDiv.remove();
    appendMessage("Bot", "⚠️ Failed to fetch alerts");
    console.error(err);
  }
});

// ---------------------- Sentiment Cards ----------------------
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

function getColor(sentiment) {
  if (sentiment === "Bullish") return "green";
  if (sentiment === "Bearish") return "red";
  return "goldenrod";
}

// ---------------------- Service Worker ----------------------
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").then((reg) => {
    reg.update();
    if (reg.waiting) reg.waiting.postMessage({ type: "SKIP_WAITING" });
  });
}
