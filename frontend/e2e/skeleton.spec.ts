import { expect, test, type Page } from "@playwright/test";

// Real backend (fake LLM): scan -> keypad text -> Hermion -> customer transcript + merchant trace.
async function scanWithKeyboard(page: Page) {
  await expect(page.locator("[data-qr-target]")).toBeVisible();
  await page.getByTestId("scan-qr").click();
  await page.getByTestId("scanner").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("session-status")).toContainText("intro", { timeout: 10_000 });
}

test("scan, chat with Hermion, see the trace, end the call", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("shop-name")).toContainText("Lakshmi Fashions");
  await expect(page.getByText("12 products in catalog")).toBeVisible();
  await expect(page.getByTestId("health")).toContainText("db: ok");

  await scanWithKeyboard(page);
  await expect(page.getByTestId("session-row").first()).toContainText("intro");
  await expect(page.getByTestId("scanner")).toHaveCount(0); // the scanner stays away during a session
  await expect(page.getByTestId("scan-qr")).toHaveCount(0);

  await page.getByTestId("more-toggle").click();
  await page.getByTestId("keypad-input").fill("Namaskaram");
  await page.getByTestId("keypad-send").click();
  const transcript = page.getByTestId("customer-transcript");
  await expect(transcript).toContainText("Namaskaram");
  await expect(transcript).toContainText("Hermion (fake LLM)");
  await expect(page.getByTestId("trace-view")).toContainText("Namaste! I am Hermion");

  await page.getByTestId("end-call").click();
  await expect(page.getByTestId("scan-qr")).toBeVisible();
  await page.getByTestId("scope-past").click();
  await expect(page.getByTestId("session-row").first()).toHaveAttribute("data-state", "exited");
});

test("dragging the scanner onto the QR starts a session; dropping elsewhere does not", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("shop-qr")).toBeVisible();
  await page.getByTestId("scan-qr").click();
  const centre = async () => {
    const box = (await page.getByTestId("scanner").boundingBox())!;
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const qr = (await page.locator("[data-qr-target]").boundingBox())!;

  let from = await centre();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x, from.y - 200, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByTestId("scan-prompt")).toBeVisible(); // missed: springs back, no session
  await expect(page.getByTestId("session-status")).toHaveCount(0);

  from = await centre();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(qr.x + qr.width / 2, qr.y + qr.height / 2, { steps: 12 });
  await expect(page.getByTestId("lock-on")).toBeVisible();
  await page.mouse.up();
  await expect(page.getByTestId("session-status")).toContainText("intro", { timeout: 10_000 });
  await expect(page.getByTestId("scanner")).toHaveCount(0);
  await page.getByTestId("end-call").click();
});

test("cancel hides the scanner; the language list comes from the shop", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("scan-qr").click();
  await expect(page.getByTestId("scanner")).toBeVisible();
  await page.getByTestId("scanner-cancel").click();
  await expect(page.getByTestId("scanner")).toHaveCount(0);

  await expect(page.locator("[data-qr-target]")).toBeVisible();
  await page.getByTestId("scan-qr").click();
  await page.getByTestId("scanner").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("session-status")).toContainText("intro", { timeout: 10_000 });
  await page.getByTestId("more-toggle").click();
  await page.getByTestId("language-section").locator("summary").click();
  await expect(page.getByTestId("language-auto")).toBeVisible();
  await expect(page.getByTestId("language-te-IN")).toContainText("Telugu");
  await page.getByTestId("end-call").click();
});
