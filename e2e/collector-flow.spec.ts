import { expect, test } from "@playwright/test";

/**
 * The Phase 1 journey in a real browser: register → create a catalogue entry → add a graded card →
 * import evidence → value it → create an insurance schedule → sell it → reports.
 */
test("collector values, insures and sells a card", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/");
  await page.getByRole("button", { name: /New here\? Create an account/ }).click();
  await page.getByLabel("Email").fill("e2e-collector@example.com");
  await page.getByLabel("Password").fill("e2e collector password");
  await page.getByLabel("Display name").fill("E2E Collector");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Portfolio", exact: true })).toBeVisible();

  // Catalogue entry + asset
  await page.getByRole("link", { name: "Add asset" }).click();
  await page.getByRole("button", { name: "Create manually" }).click();
  await page.getByLabel("Card / product name").fill("Charizard");
  await page.getByLabel("Set code").fill("base1");
  await page.getByLabel("Set name").fill("Base Set");
  await page.getByLabel("Card number").fill("4/102");
  await page.getByLabel("Edition / printing").fill("unlimited");
  await page.getByRole("button", { name: "Create catalogue entry" }).click();
  await expect(page.getByText("2 · Details for Charizard")).toBeVisible();
  await page.getByLabel("Total price paid").fill("1500");
  await page.getByLabel("Acquisition date").fill("2025-06-01");
  await page.getByLabel("Graded slab").check();
  await page.getByLabel("Grade", { exact: true }).fill("9");
  await page.getByLabel("Certification number").fill("12345678");
  await page.getByRole("button", { name: "Add to collection" }).click();

  // Evidence + valuation
  await expect(page.getByRole("heading", { name: "Charizard" })).toBeVisible();
  await page.getByRole("button", { name: "Import evidence: Synthetic demo evidence" }).click();
  await expect(page.getByRole("heading", { name: /Market evidence \(10\)/ })).toBeVisible();
  await page.getByRole("button", { name: "Run valuation" }).click();
  await expect(page.getByText(/Valuation · market ·/)).toBeVisible();
  await expect(page.getByText("Concluded unit value")).toBeVisible();
  await expect(page.getByText(/Comparables used \(\d+\)/)).toBeVisible();

  // Insurance schedule
  await page.getByRole("link", { name: "Insurance" }).click();
  await page.getByLabel("Insurer").fill("Example Mutual");
  await page.getByLabel("Policy reference").fill("POL-E2E");
  await page.getByRole("button", { name: "Create schedule" }).click();
  await page.getByRole("button", { name: "Reconcile & revalue" }).click();
  await expect(page.getByRole("cell", { name: "initial declaration", exact: true })).toBeVisible();
  await expect(page.getByText("✓ intact")).toBeVisible();

  // Sell it
  await page.getByRole("link", { name: "Portfolio" }).click();
  await page.getByRole("row", { name: /Charizard/ }).click();
  await page.getByRole("button", { name: "Mark sold" }).click();
  await page.getByPlaceholder("Sale proceeds").fill("1800");
  await page.getByPlaceholder("Venue / buyer").fill("eBay buyer");
  await page.getByRole("button", { name: "Record disposal" }).click();
  await expect(page.locator(".badge", { hasText: "disposed" })).toBeVisible();

  // Portfolio reflects the sale; realised gain = 1800 − 1500
  await page.getByRole("link", { name: "Portfolio" }).click();
  await expect(page.locator(".stat", { hasText: /^Realised gain \/ loss/ })).toContainText("300.00");

  // Insurer report + valuation report PDF
  await page.getByRole("link", { name: "Insurance" }).click();
  await expect(page.getByRole("cell", { name: "disposal", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Generate insurer report" }).click();
  await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "insurance adjustment", exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF" }).first().click();
  expect((await download).suggestedFilename()).toMatch(/^cardcore-insurance_adjustment-v1\.pdf$/);

  expect(errors).toEqual([]);
});
