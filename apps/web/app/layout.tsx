import type { Metadata } from "next";
import "@fontsource-variable/noto-sans-sc";
import "./globals.css";
import { SettingsProvider } from "../components/settings/panel";
import IdentityBoundary from "../components/identity/boundary";
export const metadata: Metadata = {
  title: "Pivot · 编辑工作台",
  description: "以对话为核心、由人类治理的科研出版工作台",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body><IdentityBoundary><SettingsProvider>{children}</SettingsProvider></IdentityBoundary></body></html>;
}
