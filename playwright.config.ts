import { defineConfig, devices } from "@playwright/test";

// Independent static-package acceptance may run alongside the business suite.
// Playwright clears outputDir before a run, so they must never share traces.
const artifactScope = process.env.DEMO_PATH ? "static-demo-" : "";
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { outputFolder: `artifacts/${artifactScope}playwright-report`, open: "never" }]],
  outputDir: `artifacts/${artifactScope}playwright-results`,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
