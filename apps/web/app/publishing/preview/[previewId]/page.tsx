import LocalPreview from "../../../../components/publishing/local-preview";

export default async function LocalPreviewPage({ params }: { params: Promise<{ previewId: string }> }) {
  const { previewId } = await params;
  return <LocalPreview key={previewId} previewId={previewId} />;
}
