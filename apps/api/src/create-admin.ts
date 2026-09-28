import { loadConfig } from "./config.js";
import { createPool, migrate } from "./db.js";
import { promoteToAdmin } from "./services/admin.js";

const email = process.argv[2];
if (!email) {
  console.error("Usage: npm run create-admin -- <email of an already-registered account>");
  process.exit(1);
}
const config = loadConfig();
const pool = createPool(config.databaseUrl);
try {
  await migrate(pool, config);
  const user = await promoteToAdmin(pool, email);
  if (!user) {
    console.error(`No account with email ${email}. Register it in the app first, then re-run.`);
    process.exitCode = 1;
  } else {
    console.log(`${user.email} is now an admin.`);
  }
} finally {
  await pool.end();
}
