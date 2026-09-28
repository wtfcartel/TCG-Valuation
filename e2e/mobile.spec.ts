import { expect, test } from "@playwright/test";

test("sign-in and dashboard fit a phone screen without horizontal scrolling", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /New here\? Create an account/ }).click();
  await page.getByLabel("Email").fill("e2e-mobile@example.com");
  await page.getByLabel("Password").fill("e2e mobile password");
  await page.getByLabel("Display name").fill("Mobile");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Portfolio", exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
