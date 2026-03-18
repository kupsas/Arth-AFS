"use client";

/**
 * ThemeToggle — a button that flips between dark and light mode.
 *
 * Note on base-ui TooltipTrigger:
 *   The new shadcn/base-ui Tooltip renders TooltipTrigger as a <button> itself.
 *   So we apply button variant styles directly to TooltipTrigger rather than
 *   nesting a <Button> inside it (which would create an illegal <button><button>).
 */

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
  const { theme, setTheme } = useTheme();

  const isDark = theme === "dark";

  return (
    <Tooltip>
      {/*
       * TooltipTrigger in base-ui IS a <button>, so we give it button styles
       * directly instead of wrapping a <Button> inside (that would nest buttons).
       */}
      <TooltipTrigger
        className={cn(buttonVariants({ variant: "ghost", size: "icon" }))}
        onClick={() => setTheme(isDark ? "light" : "dark")}
        aria-label="Toggle theme"
      >
        {isDark ? (
          <Sun className="h-4 w-4" />
        ) : (
          <Moon className="h-4 w-4" />
        )}
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {isDark ? "Switch to light mode" : "Switch to dark mode"}
      </TooltipContent>
    </Tooltip>
  );
}
