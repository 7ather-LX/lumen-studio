import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  headless: true,
  args: ["--disable-gpu", "--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1480, height: 940 } });
page.on("console", (message) => console.log("CONSOLE", message.type(), message.text()));
page.on("pageerror", (error) => console.log("PAGEERROR", error.message));
page.on("response", async (response) => {
  if (response.url().includes("/api/providers") || response.url().includes("/api/meta/presets")) {
    try {
      const text = await response.text();
      console.log("RESP", response.url(), response.status(), text.length, text.slice(0, 140));
    } catch {
      /* ignore */
    }
  }
});
await page.goto("http://127.0.0.1:5173", { waitUntil: "networkidle" });
await page.waitForTimeout(5000);
console.log(
  "COUNTS",
  JSON.stringify({
    styles: await page.locator(".style-chip").count(),
    aspects: await page.locator(".aspect-chip").count(),
    providerOptions: await page.locator(".select-field select option").count(),
    toast: await page.locator(".toast").allTextContents(),
    boot: await page.locator(".boot-screen").count(),
  }),
);
await page.screenshot({ path: "build/ui/debug.png" });
await browser.close();
