"use client";

/**
 * ThemeToggle — a button that flips between dark and light mode.
 *
 * Note on base-ui TooltipTrigger:
 *   The new shadcn/base-ui Tooltip renders TooltipTrigger as a <button> itself.
 *   So we apply button variant styles directly to TooltipTrigger rather than
 *   nesting a <Button> inside it (which would create an illegal <button><button>).
 *
 * Hydration (why we need `mounted`):
 *   - On the server, `next-themes` does not know the user's real theme yet
 *     (localStorage and `prefers-color-scheme` are browser-only).
 *   - If we rendered Sun vs Moon from `theme` immediately, the server HTML could
 *     show Moon while the client's first paint shows Sun → React throws
 *     "Hydration failed".
 *   - Fix: render the same placeholder on server AND on the first client render,
 *     then after `useEffect` runs (client-only), swap in the real icon.
 *
 * `resolvedTheme` vs `theme`:
 *   - `theme` can be "system" when the user follows OS settings.
 *   - `resolvedTheme` is the actual applied theme ("light" | "dark"), which is
 *     what we need to pick the correct icon after mount.
 */

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { buttonVariants } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { setTheme, resolvedTheme } = useTheme();

  /**
   * `false` on server and on the very first client render → same output everywhere,
   * so hydration succeeds. Flips to `true` only after this component mounts in the
   * browser (in `useEffect`).
   */
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  /** Only trust theme after mount; before that we show a neutral placeholder. */
  const isDark = mounted && resolvedTheme === "dark";

  return (
    <Tooltip>
      {/*
       * TooltipTrigger in base-ui IS a <button>, so we give it button styles
       * directly instead of wrapping a <Button> inside (that would nest buttons).
       */}
      <TooltipTrigger
        className={cn(buttonVariants({ variant: "ghost", size: "icon" }))}
        onClick={() => {
          // Avoid toggling with stale/undefined theme in the tiny window before mount.
          if (!mounted) return;
          setTheme(isDark ? "light" : "dark");
        }}
        aria-label="Toggle theme"
      >
        {/*
         * Invisible Sun keeps layout identical to the real icon (same box size).
         * Server + first client pass: always this. After mount: real Sun/Moon.
         */}
        {!mounted ? (
          <Sun className="h-4 w-4 opacity-0" aria-hidden />
        ) : isDark ? (
          <Sun className="h-4 w-4" />
        ) : (
          <Moon className="h-4 w-4" />
        )}
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {!mounted
          ? "Toggle theme"
          : isDark
            ? "Switch to light mode"
            : "Switch to dark mode"}
      </TooltipContent>
    </Tooltip>
  );
}
