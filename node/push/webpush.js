const webpush = require("web-push");

webpush.setVapidDetails(
  "mailto:support@nobroko.com",
  process.env.VAPID_PUBLIC_KEY,
  process.env.VAPID_PRIVATE_KEY
);

module.exports = webpush;
