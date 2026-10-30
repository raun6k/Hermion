import { expect, test } from "@playwright/test";

// Walking-skeleton slice: customer pane -> backend WS -> fake LLM -> customer transcript + merchant trace.
test("customer text round-trips to Hermion and shows in the merchant trace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("shop-name")).toHaveText("Lakshmi Fashions");
  await expect(page.getByText("12 products in catalog")).toBeVisible();
  await expect(page.getByTestId("health")).toContainText("db: ok");

  await page.getByTestId("start-session").click();
  await expect(page.getByTestId("session-status")).toContainText("intro");
  await expect(page.getByTestId("merchant-trace")).toContainText("session started");

  await page.getByTestId("keypad-input").fill("Namaskaram");
  await page.getByTestId("keypad-send").click();

  const transcript = page.getByTestId("customer-transcript");
  await expect(transcript).toContainText("Namaskaram");
  await expect(transcript).toContainText("Hermion (fake LLM)");
  await expect(page.getByTestId("merchant-trace")).toContainText("hermion: Namaste! I am Hermion");

  await page.getByTestId("end-call").click();
  await expect(page.getByTestId("start-session")).toBeVisible();
  await expect(page.getByTestId("merchant-trace")).toContainText("state → exited");
});
