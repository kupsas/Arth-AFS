/**
 * Public demo build — toggled at **build time** via ``NEXT_PUBLIC_DEMO_MODE``.
 *
 * When ``1`` or ``true``, the UI shows a banner, hides setup friction, and
 * treats Settings as view-only. The FastAPI side must also run with
 * ``ARTH_DEMO_MODE=1`` or these calls return 404.
 */
const raw = (process.env.NEXT_PUBLIC_DEMO_MODE ?? "").trim().toLowerCase();

export const isDemoMode = raw === "1" || raw === "true" || raw === "yes" || raw === "on";
