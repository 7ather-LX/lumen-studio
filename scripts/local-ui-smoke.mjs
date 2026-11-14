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
  await page.getByText("把想象变成画面").waitFor({ timeout: 30_000 });
  await page.locator(".select-field select").first().selectOption("local-diffusers");
  await page.locator(".prompt-shell textarea").fill("a quiet lake at blue hour, mist over the water, cinematic, soft light");
  await page.locator(".edge-chip", { hasText: "512" }).click();
  await page.getByRole("button", { name: /开始生成|生成示例画面/ }).click();
  await page.getByText("本次作品").waitFor({ timeout: 180_000 });
  await page.waitForTimeout(1500);
  const provider = await page.locator(".stage-image-meta span").first().textContent();
  const size = await page.locator(".stage-image-meta span").nth(0).textContent();
  console.log("LOCAL_OK", provider, size, "errors", JSON.stringify(errors));
  await page.screenshot({ path: "docs/screenshots/local-result.png" });
} catch (error) {
  console.error("LOCAL_FAILED", error);
  await page.screenshot({ path: "docs/screenshots/local-failure.png" });
  process.exitCode = 1;
} finally {
  await browser.close();
}
