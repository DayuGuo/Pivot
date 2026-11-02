import type { Metadata } from "next";
import "@fontsource-variable/noto-sans-sc";
import "./globals.css";
export const metadata: Metadata = {
  title: "Publishing OS · 编辑工作台",
  description: "以对话为核心、由人类治理的科研出版工作台",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
