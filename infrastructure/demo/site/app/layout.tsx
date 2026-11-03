import "@fontsource-variable/noto-sans-sc";
import "./globals.css";

export const metadata = { title: "Publishing OS · 产品演示", robots: { index: false, follow: false } };
export default function Layout({ children }: { children: React.ReactNode }) { return <html lang="zh-CN"><body>{children}</body></html>; }
