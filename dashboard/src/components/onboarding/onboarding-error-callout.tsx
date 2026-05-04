"use client"

/**
 * Consistent error surface for the onboarding wizard — short title + body + optional hint.
 * Pass already–human text from getUserFacingErrorMessage() or userMessageFromApiResponseBody().
 */

import * as React from "react"
import { AlertCircle } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export type OnboardingErrorCalloutProps = {
  title: string
  children: React.ReactNode
  className?: string
  /** e.g. "After you sign in, tap Re-scan above." */
  hint?: string
}

export function OnboardingErrorCallout({ title, children, className, hint }: OnboardingErrorCalloutProps) {
  return (
    <Card
      className={cn("border-destructive/40 bg-destructive/5", className)}
      role="alert"
    >
      <CardContent className="pt-5 pb-4">
        <div className="flex gap-3">
          <AlertCircle
            className="size-5 shrink-0 text-destructive mt-0.5"
            aria-hidden
          />
          <div className="space-y-1.5 min-w-0">
            <p className="text-sm font-medium text-foreground">{title}</p>
            <div className="text-sm text-destructive/95 leading-relaxed">{children}</div>
            {hint && (
              <p className="text-xs text-muted-foreground leading-relaxed pt-1 border-t border-border/60 mt-2">
                {hint}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
