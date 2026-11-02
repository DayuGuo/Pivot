import ProposalReview from "../../../../components/publishing/proposal-review";
export default async function PublishingReviewPage({ params }: { params: Promise<{ proposalId: string }> }) { const { proposalId } = await params; return <ProposalReview proposalId={proposalId} />; }
