import { Suspense } from "react";
import PublishingWorkspace from "../../components/publishing/workspace";

export default function PublishingLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p role="status">正在载入出版工作区…</p>}><PublishingWorkspace>{children}</PublishingWorkspace></Suspense>;
}
