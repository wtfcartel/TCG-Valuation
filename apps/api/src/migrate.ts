import { loadConfig } from "./config.js";
import { createPool, migrate } from "./db.js";

const pool = createPool(loadConfig().databaseUrl);
try {
  const ran = await migrate(pool);
  console.log(ran.length ? `Applied migrations: ${ran.join(", ")}` : "Database is up to date");
} finally {
  await pool.end();
}
