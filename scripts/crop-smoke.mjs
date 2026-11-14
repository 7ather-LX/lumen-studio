import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  headless: true,
  args: ["--disable-gpu", "--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1480, height: 940 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});

try {
  await page.goto("http://127.0.0.1:5173", { waitUntil: "domcontentloaded" });
  await page.getByText("把想象变成画面").waitFor({ timeout: 20_000 });
  await page.locator(".nav-item", { hasText: "作品" }).click();
  await page.getByText("你的图像档案").waitFor();
  await page.locator(".image-card .image-open").first().click();
  await page.getByText("作品详情").waitFor();
  await page.getByRole("button", { name: "裁切" }).click();
  await page.getByText("裁切图片").waitFor();
  await page.getByRole("button", { name: "1:1", exact: true }).click();
  await page.screenshot({ path: "docs/screenshots/crop.png" });
  await page.getByRole("button", { name: "应用裁切" }).click();
  await page.getByText(/裁切完成/).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(800);
  const badge = await page.locator(".mode-badge").first().textContent();
  const size = await page.locator(".detail-stats strong").first().textContent();
  console.log("CROP_OK", badge, size, "errors", JSON.stringify(errors));
  await page.screenshot({ path: "docs/screenshots/crop-result.png" });
} catch (error) {
  console.error("CROP_FAILED", error);
  await page.screenshot({ path: "docs/screenshots/crop-failure.png" });
  process.exitCode = 1;
} finally {
  await browser.close();
}
