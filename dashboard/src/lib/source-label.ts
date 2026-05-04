/**
 * Turn internal source keys (e.g. ``hdfc_savings``) into short UI labels without
 * exposing raw pipeline identifiers to end users.
 */
export function humanizeSourceKey(sourceKey: string | null | undefined): string {
  if (!sourceKey?.trim()) return "this account";
  return sourceKey
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}
