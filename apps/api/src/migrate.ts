import { loadConfig } from "./config.js";
import { createPool, migrate } from "./db.js";

const config = loadConfig();
const pool = createPool(config.databaseUrl);
try {
  const ran = await migrate(pool, config);
  console.log(ran.length ? `Applied migrations: ${ran.join(", ")}` : "Database is up to date");
} finally {
  await pool.end();
}
