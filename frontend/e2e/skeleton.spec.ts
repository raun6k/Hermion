import { expect, test, type Page } from "@playwright/test";

// Real backend (fake LLM): scan -> keypad text -> Hermion -> customer transcript + merchant trace.
async function scanWithKeyboard(page: Page) {
  await page.getByTestId("scan-qr").click();
  await expect(page.locator("[data-qr-target]").first()).toBeVisible();
  await page.getByTestId("scanner").focus();
  await page.keyboard.press("Enter");
  await page.getByTestId("talk-to-hermion").click();
  await expect(page.getByTestId("session-status")).toHaveAttribute("data-state", "discovery", { timeout: 10_000 });
}

test("scan, chat with Hermion, see the trace, end the call", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("shop-name")).toContainText("Lakshmi Fashions");
  await expect(page.getByTestId("status-chip")).toHaveCount(0);
  await expect(page.getByTestId("deal-banner")).toHaveCount(0);
  await expect(page.getByTestId("tab-debug")).toHaveCount(0);

  await scanWithKeyboard(page);
  await expect(page.getByTestId("session-row").first()).toHaveAttribute("data-state", "discovery");
  await expect(page.getByTestId("scanner")).toHaveCount(0); // the scanner stays away during a session

  await page.getByTestId("more-toggle").click();
  await page.getByTestId("keypad-input").fill("Namaskaram");
  await page.getByTestId("keypad-send").click();
  const transcript = page.getByTestId("customer-transcript");
  await expect(transcript).toContainText("Namaskaram");
  await expect(transcript).toContainText("Hermion (fake LLM)");
  await expect(page.getByTestId("trace-view")).toContainText("Namaste! I am Hermion");

  await page.getByTestId("end-call").click();
  await expect(page.getByTestId("shop-home")).toBeVisible();
  await page.getByTestId("leave-shop").click();
  await expect(page.getByTestId("scanner")).toHaveCount(0);
  await expect(page.getByTestId("scan-qr")).toBeVisible();
  await page.getByTestId("scope-past").click();
  await expect(page.getByTestId("session-row").first()).toHaveAttribute("data-state", "exited");
});

test("dragging the scanner onto the QR starts a session; dropping elsewhere does not", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("scan-qr").click();
  await expect(page.locator("[data-qr-target]").first()).toBeVisible();
  const centre = async () => {
    const box = (await page.getByTestId("scanner").boundingBox())!;
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const qr = (await page.locator("[data-qr-target]").first().boundingBox())!;

  let from = await centre();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 40, from.y + 300, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByTestId("scan-prompt")).toBeVisible(); // missed: springs back, no session
  await expect(page.getByTestId("session-status")).toHaveCount(0);
  // Wait for the scanner to finish springing home before starting a second drag.
  await expect(page.getByTestId("scanner")).toHaveCSS("transform", "none");

  from = await centre();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(qr.x + qr.width / 2, qr.y + qr.height / 2, { steps: 12 });
  await expect(page.getByTestId("lock-on")).toBeVisible();
  await page.mouse.up();
  await expect(page.getByTestId("shop-home")).toBeVisible({ timeout: 10_000 }); // scanning opens the shop's home
  await expect(page.getByTestId("scanner")).toHaveCount(0);
  await page.getByTestId("leave-shop").click();
});

test("the QR signs live in the customer half, none in the merchant pane", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("scan-qr").click();
  await expect(page.getByTestId("scan-strip").locator("[data-qr-target]")).toHaveCount(3);
  await expect(page.getByTestId("merchant-pane").locator("[data-qr-target]")).toHaveCount(0);
});

test("the shop page greets a new customer, and the language picker has a fixed size", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("scan-qr").click();
  await expect(page.locator("[data-qr-target]").first()).toBeVisible();
  await page.getByTestId("scanner").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("shop-page")).toHaveAttribute("aria-label", "Lakshmi Fashions");
  await expect(page.getByTestId("shop-page")).toContainText("cotton");
  await page.getByTestId("language-button").click();
  const box = (await page.locator('[role="dialog"][aria-modal="true"]').boundingBox())!;
  expect(box.width / box.height).toBeCloseTo(270 / 360, 1); // fixed size whatever the phone scale
  await page.getByTestId("language-close").click();
  await page.getByTestId("leave-shop").click();
});
