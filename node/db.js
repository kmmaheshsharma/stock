// PostgreSQL connection helper
const dns = require("dns");
dns.setDefaultResultOrder("ipv4first");
const { Pool } = require('pg');
require('dotenv').config();

const pool = new Pool({
  host: process.env.PG_HOST,
  port: Number(process.env.PG_PORT || 5432),
  database: process.env.PG_DATABASE,
  user: process.env.PG_USER,
  password: process.env.PG_PASSWORD,
  ssl: process.env.PG_SSL === 'true' ? { rejectUnauthorized: false } : false
});
pool.on("connect", () => {
  console.log("✅ Connected to PostgreSQL");
});

pool.on("error", (err) => {
  console.error("❌ PostgreSQL error", err);
});

module.exports = {
  query: (text, params) => pool.query(text, params),
  pool
};
module.exports = {
  query: (text, params) => pool.query(text, params),
  pool
};
