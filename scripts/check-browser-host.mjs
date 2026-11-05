// Fail before database work when an installed engine lacks host libraries.
// Launching a blank page does not contact the application or a model provider.
import { chromium, firefox, webkit } from "playwright";

for (const [name, engine] of Object.entries({ chromium, firefox, webkit })) {
  let browser;
  try {
    browser = await engine.launch({ timeout: 30_000 });
    const page = await browser.newPage();
    await page.setContent("<p>browser-host-ready</p>");
    if (await page.locator("p").textContent() !== "browser-host-ready") throw new Error("blank page failed");
    console.log(`${name} host ready: ${browser.version()}`);
  } catch {
    console.error(`${name} cannot launch. Check Playwright host libraries before running the full gate.`);
    process.exitCode = 1;
    break;
  } finally {
    if (browser) await browser.close();
  }
}
