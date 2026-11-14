import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";

const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const base = process.env.LUMEN_UI_URL || "http://127.0.0.1:5173";
const outDir = path.resolve("build", "ui");
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: edge,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--hide-scrollbars"],
});
const page = await browser.newPage({ viewport: { width: 1480, height: 940 }, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(`PAGEERROR ${error.message}`));

const shot = async (name) => {
  await page.screenshot({ path: path.join(outDir, `${name}.png`) });
  console.log("SHOT", path.join(outDir, `${name}.png`));
};

try {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.getByText("把想象变成画面").waitFor({ timeout: 20_000 });
  await page.waitForTimeout(700);
  await shot("01-create");

  const prompt = page.locator(".prompt-shell textarea");
  await prompt.fill("雨夜的东京小巷，霓虹倒映在积水中，电影感广角镜头，湿润空气");
  await page.getByRole("button", { name: /生成示例画面|开始生成/ }).click();
  await page.getByText("本次作品").waitFor({ timeout: 45_000 });
  await page.waitForTimeout(1200);
  await shot("02-result");

  await page.locator(".nav-item", { hasText: "作品" }).click();
  await page.getByText("你的图像档案").waitFor({ timeout: 10_000 });
  await page.waitForTimeout(1000);
  await shot("03-gallery");

  const firstCard = page.locator(".image-card .image-open").first();
  if (await firstCard.count()) {
    await firstCard.click();
    await page.getByText("作品详情").waitFor({ timeout: 5000 });
    await page.waitForTimeout(600);
    await shot("04-detail");
    await page.locator(".modal-header .icon-button").click();
  }

  await page.locator(".nav-item", { hasText: "模型" }).click();
  await page.getByText("选择画面的发动机").waitFor({ timeout: 10_000 });
  await page.waitForTimeout(1200);
  await shot("05-models");

  await page.locator(".nav-item", { hasText: "学习" }).click();
  await page.getByText("越画，越像你").waitFor({ timeout: 10_000 });
  await page.waitForTimeout(800);
  await shot("06-learning");

  await page.locator(".nav-item", { hasText: "设置" }).click();
  await page.getByText("让工作流适合你").waitFor({ timeout: 10_000 });
  await page.waitForTimeout(500);
  await shot("07-settings");

  console.log("CONSOLE_ERRORS", JSON.stringify(consoleErrors, null, 2));
} catch (error) {
  console.error("UI_SMOKE_FAILED", error);
  await shot("99-failure");
  process.exitCode = 1;
} finally {
  await browser.close();
}
