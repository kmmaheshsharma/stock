const axios = require("axios");
const fs = require("fs");
const FormData = require("form-data");

/**
 * Send TEXT message (existing)
 */
exports.sendWhatsApp = async (to, message) => {
  await axios.post(
    `https://graph.facebook.com/v18.0/${process.env.PHONE_ID}/messages`,
    {
      messaging_product: "whatsapp",
      to,
      text: { body: message }
    },
    {
      headers: {
        Authorization: `Bearer ${process.env.ACCESS_TOKEN}`,
        "Content-Type": "application/json"
      }
    }
  );
};

/**
 * Send IMAGE message (NEW)
 */
exports.sendWhatsAppImage = async (to, imagePath, caption = "") => {
  // 1️⃣ Upload image to WhatsApp
  const form = new FormData();
  form.append("file", fs.createReadStream(imagePath));
  form.append("type", "image/png");
  form.append("messaging_product", "whatsapp");

  const uploadRes = await axios.post(
    `https://graph.facebook.com/v18.0/${process.env.PHONE_ID}/media`,
    form,
    {
      headers: {
        Authorization: `Bearer ${process.env.ACCESS_TOKEN}`,
        ...form.getHeaders()
      }
    }
  );

  const mediaId = uploadRes.data.id;

  // 2️⃣ Send image using media ID
  await axios.post(
    `https://graph.facebook.com/v18.0/${process.env.PHONE_ID}/messages`,
    {
      messaging_product: "whatsapp",
      to,
      type: "image",
      image: {
        id: mediaId,
        caption
      }
    },
    {
      headers: {
        Authorization: `Bearer ${process.env.ACCESS_TOKEN}`,
        "Content-Type": "application/json"
      }
    }
  );
};
