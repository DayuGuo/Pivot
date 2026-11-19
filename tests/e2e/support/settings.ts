import type { Page } from "@playwright/test";

export async function selectTheme(page: Page, value: string) {
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "设置", exact: true });
  await settings.getByRole("tab", { name: "外观", exact: true }).click();
  await settings.getByLabel("界面主题", { exact: true }).selectOption(value);
  await settings.getByRole("button", { name: "关闭设置", exact: true }).click();
}
