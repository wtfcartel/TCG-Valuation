import { defineConfig, devices } from "@playwright/test";

const PORT = 8181;
export const E2E_DATABASE_URL = process.env.E2E_DATABASE_URL ?? "postgres://cardcore:cardcore@localhost:5432/cardcore_e2e";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: {
    command: "npm run build -w @cardcore/web && npx tsx e2e/reset-db.ts && npx tsx apps/api/src/server.ts",
    cwd: "..",
    url: `http://localhost:${PORT}/api/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      NODE_ENV: "development",
      PORT: String(PORT),
      DATABASE_URL: E2E_DATABASE_URL,
      JWT_SECRET: "e2e-only-secret-0123456789",
      WEB_DIST_DIR: "apps/web/dist",
      ENABLE_DEMO_SOURCE: "true",
      ENABLE_ECB_FX: "false",
      ENABLE_TCGDEX: "false",
      PHOTO_STORAGE_DIR: "/tmp/cardcore-e2e-photos",
    },
  },
});
