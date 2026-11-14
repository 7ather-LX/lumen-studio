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
  await page.locator(".edge-chip", { hasText: "512" }).click();
  await page.getByRole("button", { name: /动漫角色设定/ }).click();
  await page.getByPlaceholder("silver long hair, twin tails").fill("silver long hair");
  await page.getByPlaceholder("amber eyes, detailed eyes").fill("red eyes");
  await page.getByPlaceholder("black school uniform, red ribbon").fill("black sailor suit");
  await page.getByPlaceholder("gentle smile, confident").fill("gentle smile");
  await page.getByPlaceholder("cherry blossoms, blue sky").fill("cherry blossoms, soft daylight");
  await page.getByRole("button", { name: "加入提示词" }).click();
  await page.locator(".prompt-shell textarea").waitFor();
  const afterCharacter = await page.locator(".prompt-shell textarea").inputValue();
  if (!afterCharacter.includes("silver long hair")) throw new Error("character builder failed");

  const llmButton = page.getByRole("button", { name: /LLM 完善/ });
  await llmButton.waitFor({ timeout: 10_000 });
  await llmButton.click();
  await page.waitForFunction(
    () => {
      const element = document.querySelector(".prompt-shell textarea");
      return element && element.value.includes("1girl");
    },
    { timeout: 180_000 },
  );
  const enhanced = await page.locator(".prompt-shell textarea").inputValue();
  console.log("ANIME_PROMPT", enhanced.slice(0, 500));
  await page.screenshot({ path: "docs/screenshots/anime-prompt.png" });

  await page.getByRole("button", { name: /开始生成/ }).click();
  await page.getByText("本次作品").waitFor({ timeout: 240_000 });
  await page.waitForTimeout(1200);
  console.log("ANIME_OK", JSON.stringify(errors));
  await page.screenshot({ path: "docs/screenshots/anime-result.png" });
} catch (error) {
  console.error("ANIME_FAILED", error);
  await page.screenshot({ path: "docs/screenshots/anime-failure.png" });
  process.exitCode = 1;
} finally {
  await browser.close();
}
