import { expect, test } from "@playwright/test";

// Real backend: catalog inline edit shows the server's validation error and keeps the stored value.
test("catalog rejects a minimum above the target and accepts a valid edit", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tab-catalog").click();
  await page.getByTestId("row-SHIRT-BLU-M").click();
  const minimum = page.getByTestId("cell-SHIRT-BLU-M-minimum_price");
  await expect(minimum).toHaveValue("750");

  await minimum.fill("900");
  await minimum.press("Enter");
  await expect(page.getByTestId("error-SHIRT-BLU-M-minimum_price")).toContainText("between minimum and listed");
  await minimum.press("Escape");
  await expect(minimum).toHaveValue("750");

  await page.getByTestId("row-SHIRT-BLU-L").click();
  const stock = page.getByTestId("cell-SHIRT-BLU-L-available_stock");
  await stock.fill("3");
  await stock.press("Enter");
  await page.reload();
  await page.getByTestId("tab-catalog").click();
  await page.getByTestId("row-SHIRT-BLU-L").click();
  await expect(page.getByTestId("cell-SHIRT-BLU-L-available_stock")).toHaveValue("3");
  const restore = page.getByTestId("cell-SHIRT-BLU-L-available_stock");
  await restore.fill("2");
  await restore.press("Enter");
});

test("shop settings save the escalation and add-on choices", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tab-shop").click();
  await expect(page.getByTestId("languages-input")).toHaveCount(0); // languages are not merchant-edited
  await page.getByTestId("escalation-select").selectOption("never");
  await page.getByTestId("save-shop").click();
  await expect(page.getByText("✓ Saved")).toBeVisible();
  await page.getByTestId("escalation-select").selectOption("rare");
  await page.getByTestId("save-shop").click();
});

test("the header omits status and waiting controls, and the avatar switches shops", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("status-chip")).toHaveCount(0);
  await expect(page.getByTestId("deal-banner")).toHaveCount(0);
  await expect(page.getByTestId("tab-debug")).toHaveCount(0);
  await page.getByTestId("avatar").click();
  await expect(page.getByTestId("avatar-menu")).toContainText("Choose a shop to view its customers, approvals, products, settings, and insights.");
  await expect(page.getByTestId("shop-M002")).not.toContainText("SP Road");
  await page.getByTestId("shop-M002").click();
  await expect(page.getByTestId("shop-name")).toContainText("Ameerpet Electronics");
  await expect(page.getByTestId("shop-address")).toHaveText("SP Road, Bengaluru");
  await page.getByTestId("avatar").click();
  await page.getByTestId("shop-M001").click();
  await expect(page.getByTestId("shop-name")).toContainText("Lakshmi");
  await expect(page.getByTestId("shop-address")).toHaveText("Jayanagar 4th Block, Bengaluru");
  await page.getByTestId("avatar").click();
  await page.getByTestId("shop-M003").click();
  await expect(page.getByTestId("shop-name")).toContainText("Charminar Furniture");
  await expect(page.getByTestId("shop-address")).toHaveText("Rajajinagar, Bengaluru");
});

test("catalog product details are grouped and goal type opens an accessible custom listbox", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tab-catalog").click();
  const goalType = page.getByTestId("goal-type-select-0");
  await goalType.press("Enter");
  await expect(page.getByRole("listbox", { name: "Goal type" })).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");

  await page.getByTestId("row-SHIRT-BLU-M").click();
  const drawer = page.getByTestId("product-drawer");
  await expect(drawer).toContainText("Price and margin");
  await expect(drawer).toContainText("Cost and inventory");
  await expect(drawer).toContainText("What Hermion tells customers");
});

test("shop settings are edited directly and goals live with the catalog", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("tab-shop").click();
  await expect(page.getByTestId("shop-settings")).toBeVisible();
  await expect(page.getByTestId("setup-input")).toHaveCount(0);
  await expect(page.getByTestId("upsell-toggle")).toHaveCount(0);
  await expect(page.getByText("Let customers ask for one price for several items")).toHaveCount(0);
  await page.getByRole("textbox", { name: /About the shop/ }).fill("A shop description edited directly.");
  await page.getByTestId("save-shop").click();
  await expect(page.getByRole("status")).toContainText("Saved");
  await page.getByTestId("tab-catalog").click();
  await expect(page.getByTestId("goals")).toBeVisible();
});
