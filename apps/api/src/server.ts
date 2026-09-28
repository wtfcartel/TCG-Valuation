import { buildApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createPool, migrate } from "./db.js";
import { startEcbScheduler } from "./services/ecb.js";

const config = loadConfig();
const pool = createPool(config.databaseUrl);
await migrate(pool, config);
if (config.adminEmails.length) {
  await pool.query(`UPDATE users SET role = 'admin' WHERE email = ANY($1) AND role <> 'admin'`, [config.adminEmails]);
}
const app = await buildApp({ config, pool, logger: true, trustProxy: true });
if (config.enableEcbFx) startEcbScheduler(pool, app.log);

const shutdown = async () => {
  await app.close();
  await pool.end();
  process.exit(0);
};
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);

await app.listen({ port: config.port, host: "0.0.0.0" });
