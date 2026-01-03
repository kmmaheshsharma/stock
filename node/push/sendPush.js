const webpush = require("./webpush");
const { pool } = require("../db");

async function sendPushToUser(userId, payload) {
  const result = await pool.query(
    "SELECT * FROM push_subscriptions WHERE user_id = $1",
    [userId]
  );

  for (const sub of result.rows) {
    try {
      await webpush.sendNotification(
        {
          endpoint: sub.endpoint,
          keys: {
            p256dh: sub.p256dh,
            auth: sub.auth
          }
        },
        JSON.stringify(payload)
      );
    } catch (err) {
      console.error("❌ Push failed:", err.message);
    }
  }
}

module.exports = { sendPushToUser };
