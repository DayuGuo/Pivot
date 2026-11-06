import { withRequestTimeout } from "../browser";
import { roleLabels } from "../publishing/types";

export type IdentitySnapshot = {
  user: { id: string; name: string; email: string; role: string };
  journal: { id: string; name: string };
  active_role: string;
  roles: string[];
  csrf_token: string;
};

export class IdentityError extends Error {
  constructor(public status: number) { super("identity_request_failed"); }
}

export const knownRole = (role: unknown): role is string => typeof role === "string" && Object.hasOwn(roleLabels, role);
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;

export function validIdentity(value: unknown): value is IdentitySnapshot {
  if (!record(value) || !record(value.user) || !record(value.journal)) return false;
  const { user, journal, roles, active_role, csrf_token } = value;
  return [user.id, user.name, user.email, journal.id, journal.name, csrf_token].every(text) &&
    knownRole(active_role) && user.role === active_role && Array.isArray(roles) &&
    roles.length > 0 && roles.length <= Object.keys(roleLabels).length && roles.every(knownRole) &&
    new Set(roles).size === roles.length && roles.includes(active_role);
}

export async function readIdentities(signal: AbortSignal): Promise<IdentitySnapshot> {
  return withRequestTimeout(15000, signal, async boundedSignal => {
    const response = await fetch("/api/auth/identities", { credentials: "same-origin", cache: "no-store", signal: boundedSignal });
    if (!response.ok) throw new IdentityError(response.status);
    const value: unknown = await response.json();
    if (!validIdentity(value)) throw new IdentityError(502);
    return value;
  });
}

export const isSessionFailure = (error: unknown) => error instanceof IdentityError && [401, 403].includes(error.status);
