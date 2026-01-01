document.getElementById("test-alert").addEventListener("click", () => {
  const alertsDiv = document.getElementById("alerts");
  const msg = document.createElement("div");
  msg.textContent = "✅ Test alert received at " + new Date().toLocaleTimeString();
  alertsDiv.prepend(msg);
});
