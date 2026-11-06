import IdentityConfirmation from "../../components/identity/confirmation";

export default async function IdentityPage({ searchParams }: { searchParams: Promise<{ role?: string | string[] }> }) {
  const { role } = await searchParams;
  return <IdentityConfirmation requestedRole={typeof role === "string" ? role : null} />;
}
