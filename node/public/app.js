const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const cardsEl = document.getElementById("sentiment-cards");
const alertsBtn = document.getElementById("alerts-btn");
const signinBtn = document.getElementById("signin-btn");
const signupBtn = document.getElementById("signup-btn");
const signupScreen = document.getElementById("signup-screen");
const chatScreen = document.getElementById("chat-screen");
const signupForm = document.getElementById("signup-form");
let isAppInForeground = true;
// Clear previous content on load
messagesEl.innerHTML = "";
cardsEl.innerHTML = "";
let socket;
let deferredPrompt;
document.addEventListener('visibilitychange', function() {
  isAppInForeground = !document.hidden;
  console.log("App is in " + (isAppInForeground ? "foreground" : "background"));

  // Store in localStorage for local reference
  localStorage.setItem('isAppInForeground', isAppInForeground);

  // Send the state to the server (e.g., index.js or backend)
  fetch('/api/update-visibility', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ isAppInForeground })
  })
  .then(response => response.json())
  .then(data => console.log("Visibility state sent to server:", data))
  .catch(error => console.error("Error sending visibility state to server:", error));
});
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;

  const btn = document.getElementById("install-btn");
  if (btn) btn.style.display = "block";
});
document.getElementById("install-btn")?.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  console.log("Install outcome:", outcome);
  deferredPrompt = null;
});
// Convert VAPID key from base64 string to Uint8Array
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
async function getVapidKey() {
  const res = await fetch("/api/push/public-key");
  const data = await res.json();
  return data.publicKey;
}
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach(b => binary += String.fromCharCode(b));
  return btoa(binary);
}
async function enablePushNotifications() {
  const userId = await getAndCheckUser();
  console.log("enablePushNotifications called"); // debug line
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return;

  const reg = await navigator.serviceWorker.ready;

  const vapidKey = await getVapidKey();  

  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey)
  });
  const p256dh = arrayBufferToBase64(subscription.getKey("p256dh"));
  const auth = arrayBufferToBase64(subscription.getKey("auth"));
  // Send subscription + userId to backend
  await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      endpoint: subscription.endpoint,
      keys: { p256dh, auth }
    })
  });
  console.log("✅ Push notifications enabled!");
}

function initSocket(userId) {
  if (!userId) return;

  // Disconnect existing socket if any
  if (socket) socket.disconnect();

  // Connect with userId in query
  socket = io("https://aiwhatupaccountant-production.up.railway.app", {
    query: { userId }
  });

  socket.on("connect", () => {
    console.log("Connected to server with socket ID:", socket.id);
  });

  socket.on("alertMessage", (data) => {
    const { text, chart, source } = data;
    const msgEl = document.createElement("div");
    msgEl.className = "message bot-message";

    // First, add the update text
    msgEl.innerHTML = text;

    // If the chart exists, create and append the chart image
    if (chart) {
      const br = document.createElement("br"); // create a line break
      msgEl.appendChild(br);                   // add it before the image

      const img = document.createElement("img");
      img.src = chart;
      img.style.maxWidth = "400px";   // max width
      img.style.maxHeight = "250px";  // max height
      img.style.display = "block";    // ensures it stays on its own line
      img.style.margin = "10px 0";    // space above/below
      msgEl.appendChild(img);         // append the image after the text
    }

    // Mark the update as read based on the symbol and source
    const match = text.match(/<b>([^<]+)<\/b>/); // Extract symbol from text if in <b> tags
    const symbol = match ? match[1].trim() : null;
    if (symbol) markUpdateAsRead(symbol, source);

    // Append the message element to the chat
    messagesEl.appendChild(msgEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}
async function getAndCheckUser() {
  const phone = localStorage.getItem("userPhone");
  console.log("Fetched phone:", phone);

  if (!phone) return null; // no phone stored

  try {
    const res = await fetch('/api/check-user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });

    const data = await res.json();
    if (data.status === 'existing') {
      localStorage.setItem("userId", data.userId);
      return data.userId;
    }
    return null; // user not found
  } catch (err) {
    console.error("Error checking user:", err);
    return null;
  }
}

window.onload = async function() {
  const userId = await getAndCheckUser();

  if (userId) {
    // Existing user: show chat
    signupScreen.style.display = "none";
    chatScreen.style.display = "";
    initChatBot(userId);
    initSocket(userId);    
    loadUserUpdates();
  } else {
    // New user: show signup
    signupScreen.style.display = "";
    chatScreen.style.display = "none";    
  }
};

// ---------------------- User Updates in Chat Bot ----------------------

async function loadUserUpdates() {
  const userId = localStorage.getItem("userId");
  if (!userId) return;

  try {   
    const res = await fetch("/api/user/updates", {
      method: "POST",  // Change to POST
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ userId })     
    });
    const data = await res.json();

    if (!data.updates || data.updates.length === 0) {
      //appendMessage("Bot", "You don't have any new updates at the moment. Please check back later for the latest stock alerts. 🔔");
      return;
    }

    data.updates.forEach(update => {
      console.log(update.symbol, update.last_update_summary);

      const div = document.createElement("div");
      div.className = "update-card";
      div.innerHTML = `
        <strong>${update.symbol}</strong>
        <p>${update.last_update_summary}</p>
        <small>${new Date(update.last_update_at).toLocaleTimeString()}</small>
      `;
      if (update.raw_graph_base64) {
        const chartImg = document.createElement("img");
        chartImg.src = update.raw_graph_base64;
        chartImg.style.maxWidth = "400px";   // Adjust as per your layout
        chartImg.style.maxHeight = "250px";  // Adjust as per your layout
        chartImg.style.display = "block";    // Ensure it stays on its own line
        chartImg.style.margin = "10px 0";    // Space above/below the image
        div.appendChild(chartImg);           // Append the image to the div
      }
      // Append update as a message in chat (like a normal bot message)
      appendMessage("Bot", div.innerHTML);

      // Mark this update as read
      markUpdateAsRead(update.symbol, update.source);
    });
  } catch (err) {
    console.error("Failed to load user updates:", err);
    appendMessage("Bot", "⚠️ Failed to load updates. Please try again.");
  }
}

// Function to mark update as read (this is optional, depending on your backend)
async function markUpdateAsRead(symbol, source) {
  try {
    await fetch("/api/user/updates/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, source })
    });
    console.log(`Marked ${symbol} as read from ${source}`);
  } catch (err) {
    console.error("Error marking update as read:", err);
  }
}
// ---------------------- Append chat messages ----------------------
function appendMessage(sender, html, chart) {
  const div = document.createElement("div");
  div.className = sender === "You" ? "user-msg" : "bot-msg";

  // Message content
  const msgContentDiv = document.createElement("div");
  msgContentDiv.className = "msg-content";
  msgContentDiv.innerHTML = html;
  div.appendChild(msgContentDiv);

  // Append chart if provided
  if (chart) {
    const chartImg = document.createElement("img");
    chartImg.src = chart;
    chartImg.style.maxWidth = "400px";   // Adjust to layout
    chartImg.style.maxHeight = "250px";  // Adjust to layout
    chartImg.style.display = "block";    // Force new line
    chartImg.style.margin = "10px 0";    // Space above/below image
    div.appendChild(chartImg);
  }

  // Append time after the chart
  const msgTimeDiv = document.createElement("div");
  msgTimeDiv.className = "msg-time";
  msgTimeDiv.innerHTML = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  div.appendChild(msgTimeDiv);

  // Add the message div to the messages container
  messagesEl.appendChild(div);
  setTimeout(() => {
    // Ensure that the scroll is at the bottom after the message is added
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }, 50); // A small delay to ensure the message is appended before scrolling
}


// ---------------------- Typing simulation ----------------------
function botTypingIndicator() {
  const div = document.createElement("div");
  div.className = "bot-msg";
  div.innerHTML = `<div class="msg-content">Bot is typing...</div><div class="msg-time">...</div>`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
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
    const res = await fetch("/api/check-user", {
      method: "POST", // Ensure the correct HTTP method
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ phone }), // Send phone in request body
    });

    // Check if the response was successful
    if (!res.ok) {
      throw new Error("Network response was not ok");
    }

    const data = await res.json();

    // Check if userId exists in the response
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

// ---------------------- Handle web chat messages ----------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg) return;

  appendMessage("You", msg);
  input.value = "";

  const typingDiv = botTypingIndicator();
  const phone = localStorage.getItem("userPhone");
  const userId = localStorage.getItem("userId");
    try {
    // Send message to backend that uses processMessage (like handleMessage)
    const res = await fetch("/api/webchat", { // <-- create this endpoint
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, phone: phone, userId: userId })
    });
    const data = await res.json();

    // simulate typing delay
    await delay(Math.random() * 1000 + 1000);

    typingDiv.remove();
    appendMessage("Bot", data.text, data.chart); // display the bot response
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
    await fetch("/api/alerts");
    await res.json();
    typingDiv.remove();
    appendMessage("Bot", "🔔 Checking alerts... You’ll be notified if anything triggers.");

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

function initChatBot(userId) {
  console.log("Chat initialized for user", userId);
  loadSentiments();
  setInterval(loadSentiments, 30000);
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
  navigator.serviceWorker
    .register("/sw.js")
    .then(() => {
      console.log("Service Worker registered");
      enablePushNotifications(); // call here after registration
    })
    .catch(console.error);
}
