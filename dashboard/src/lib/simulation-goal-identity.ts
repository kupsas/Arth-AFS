/**
 * Hypothetical simulation goals have `id: null`; React list keys must stay stable while
 * the user edits `name`, priority, etc. The engine ignores this field on the wire.
 */
export function newSimulationClientRowId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `hyp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
