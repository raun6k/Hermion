import { expect, test } from "@playwright/test";

// Real backend: catalog inline edit shows the server's validation error and keeps the stored value.
test("catalog rejects a minimum above the target and accepts a valid edit", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tab-catalog").click();
  const minimum = page.getByTestId("cell-SHIRT-BLU-M-minimum_price");
  await expect(minimum).toHaveValue("750");

  await minimum.fill("900");
  await minimum.press("Enter");
  await expect(page.getByTestId("error-SHIRT-BLU-M-minimum_price")).toContainText("between minimum and listed");
  await minimum.press("Escape");
  await expect(minimum).toHaveValue("750");

  const stock = page.getByTestId("cell-SHIRT-BLU-L-available_stock");
  await stock.fill("3");
  await stock.press("Enter");
  await page.reload();
  await page.getByTestId("tab-catalog").click();
  await expect(page.getByTestId("cell-SHIRT-BLU-L-available_stock")).toHaveValue("3");
  const restore = page.getByTestId("cell-SHIRT-BLU-L-available_stock");
  await restore.fill("2");
  await restore.press("Enter");
});

test("shop settings validate languages against the backend", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tab-shop").click();
  await page.getByTestId("languages-input").fill("hi-IN, fr-FR");
  await page.getByTestId("save-shop").click();
  await expect(page.getByTestId("shop-error")).toContainText("fr-FR");
});
