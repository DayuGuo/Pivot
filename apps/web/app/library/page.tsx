import { Suspense } from "react";
import LibraryWorkspace from "../../components/library/workspace";
export default function LibraryPage() {
  return <Suspense fallback={<p role="status">正在载入内部资料…</p>}><LibraryWorkspace /></Suspense>;
}
