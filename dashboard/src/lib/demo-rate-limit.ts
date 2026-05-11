/**
 * Demo chat rate limit — 15 messages per 30-minute sliding window.
 *
 * Stored in localStorage so the window survives page reloads and DB resets (the demo
 * "Reset" button wipes the server-side SQLite copy, but the clock keeps ticking here).
 * After 30 minutes from the first message in a window the counter auto-resets.
 */

export const DEMO_RATE_LIMIT_MAX = 15;
export const DEMO_RATE_LIMIT_WINDOW_MS = 30 * 60 * 1000; // 30 minutes

const KEY_WINDOW_START = "arth:demo:ratelimit:window_start";
const KEY_COUNT = "arth:demo:ratelimit:count";

export interface DemoRateLimitState {
  count: number;
  windowStart: number | null; // epoch ms when current window started
  remaining: number;
  msUntilReset: number;       // > 0 only when the limit is hit
  isLimited: boolean;
}

function _read(): { count: number; windowStart: number | null } {
  if (typeof window === "undefined") return { count: 0, windowStart: null };
  try {
    const ws = localStorage.getItem(KEY_WINDOW_START);
    const c = localStorage.getItem(KEY_COUNT);
    return {
      count: c ? parseInt(c, 10) : 0,
      windowStart: ws ? parseInt(ws, 10) : null,
    };
  } catch {
    return { count: 0, windowStart: null };
  }
}

function _write(count: number, windowStart: number): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY_WINDOW_START, String(windowStart));
    localStorage.setItem(KEY_COUNT, String(count));
  } catch {
    // private/quota mode — silently degrade
  }
}

function _buildState(count: number, windowStart: number | null): DemoRateLimitState {
  const now = Date.now();
  if (!windowStart || now - windowStart >= DEMO_RATE_LIMIT_WINDOW_MS) {
    return { count: 0, windowStart: null, remaining: DEMO_RATE_LIMIT_MAX, msUntilReset: 0, isLimited: false };
  }
  const remaining = Math.max(0, DEMO_RATE_LIMIT_MAX - count);
  const isLimited = remaining === 0;
  return {
    count,
    windowStart,
    remaining,
    msUntilReset: isLimited ? Math.max(0, DEMO_RATE_LIMIT_WINDOW_MS - (now - windowStart)) : 0,
    isLimited,
  };
}

/** Read current state without touching storage. */
export function getDemoRateLimitState(): DemoRateLimitState {
  const { count, windowStart } = _read();
  return _buildState(count, windowStart);
}

/**
 * Record one message being sent. Starts the window on first message, or opens a
 * new window if the previous one expired. Returns state AFTER recording.
 * Call this only when a message is actually transmitted — not on blocked attempts.
 */
export function recordDemoMessage(): DemoRateLimitState {
  const { count, windowStart } = _read();
  const now = Date.now();
  const expired = !windowStart || now - windowStart >= DEMO_RATE_LIMIT_WINDOW_MS;
  const newWindowStart = expired ? now : windowStart!;
  const newCount = expired ? 1 : count + 1;
  _write(newCount, newWindowStart);
  return _buildState(newCount, newWindowStart);
}

/** Format milliseconds as MM:SS for the countdown. */
export function formatCountdown(ms: number): string {
  const totalSeconds = Math.ceil(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
