import { Suspense } from "react";
import LibraryWorkspace from "../../../../components/library/workspace";
export default async function EvaluationPage({ params }: { params: Promise<{ packageId: string }> }) {
 const {packageId}=await params;
 return <Suspense fallback={<p role="status">正在载入评价…</p>}><LibraryWorkspace evaluationId={packageId}/></Suspense>;
}
