import { Suspense } from "react";
import LibraryWorkspace from "../../../../components/library/workspace";
export default async function DocumentImportPage({ params }: { params: Promise<{ importId: string }> }) {
  const { importId } = await params;
  return <Suspense fallback={<p role="status">正在读取导入核对…</p>}><LibraryWorkspace importId={importId} /></Suspense>;
}
