import { Suspense } from "react";
import LibraryWorkspace from "../../../../components/library/workspace";
export default async function LibraryReviewPage({ params }: { params: Promise<{ versionId: string }> }) {
  const { versionId } = await params;
  return <Suspense fallback={<p role="status">正在载入核对版本…</p>}><LibraryWorkspace reviewVersionId={versionId} /></Suspense>;
}
