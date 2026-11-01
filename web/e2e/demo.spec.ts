import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function accessible(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(violations.filter((item) => ["serious", "critical"].includes(item.impact ?? "")).map((item) => item.id)).toEqual([]);
}

async function tabTo(page: Page, name: string) {
  for (let presses = 0; presses < 120; presses++) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.textContent?.trim());
    if (focused === name) return;
  }
  throw new Error(`"${name}" cannot be reached with the keyboard`);
}

const calls: string[] = [];
test.afterEach(() => expect(calls, "demo mode needs no backend").toEqual([]));
test.beforeEach(async ({ page }) => {
  page.on("request", (request) => request.url().includes("/api/") && calls.push(request.url()));
  await page.goto("/");
  await expect(page.getByText("Demo mode · recorded runs from the deployed system")).toBeVisible();
});

test("the empty state offers the suggestions and passes axe", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Upload this month's invoices" })).toBeEnabled();
  await expect(page.getByRole("textbox", { name: "Message" })).toBeDisabled();
  await accessible(page);
});

test("a clerk reviews and approves a recorded batch with the keyboard only", async ({ page }) => {
  await tabTo(page, "Batch upload, correction and approval");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Ready for review in/)).toHaveCount(3);
  await accessible(page);
  await tabTo(page, "Approve");
  await page.keyboard.press("Enter");
  await expect(page.locator("article").first().getByText("Approved", { exact: true })).toBeVisible();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.locator("article").first().getByText(/Corrected by Ana Clerk · Field: Due date · Before: 2026-04-21 · After: 2026-12-31/)).toBeVisible();
  await accessible(page);
});

test("the lead resolves a duplicate with a reason and the assistant cites invoices", async ({ page }) => {
  await tabTo(page, "Duplicate resolved by the lead");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Exact duplicate")).toBeVisible();
  await expect(page.getByRole("textbox", { name: /Reason/ })).not.toBeEmpty();
  await tabTo(page, "Approve");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Assistant lists invoices awaiting approval" }).click();
  await expect(page.getByRole("list", { name: "Sources" })).toContainText("Invoice F2026-0558");
  await accessible(page);
});
