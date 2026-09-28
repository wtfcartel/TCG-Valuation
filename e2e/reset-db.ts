import pg from "pg";

/** Run before the e2e server starts: every run begins from an empty database (the server migrates on start). */
const url = process.env.DATABASE_URL;
if (!url || !/_e2e\b/.test(url)) throw new Error(`Refusing to reset a database that is not an *_e2e database: ${url}`);
const client = new pg.Client({ connectionString: url });
await client.connect();
await client.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
await client.end();
