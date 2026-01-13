// PostgreSQL connection helper (Supabase IPv4 Pooler SAFE)
const dns = require("dns");
dns.setDefaultResultOrder("ipv4first");

const { Pool } = require("pg");
require("dotenv").config();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

pool.on("connect", () => {
  console.log("✅ Connected to Supabase PostgreSQL (IPv4)");
});

pool.on("error", (err) => {
  console.error("❌ PostgreSQL error", err);
});

module.exports = {
  query: (text, params) => pool.query(text, params),
  pool
};
