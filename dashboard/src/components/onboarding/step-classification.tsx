"use client"

/**
 * Inline **classification checkpoint** (Track 2 Phase 5a).
 *
 * Thin wrapper around ``ClassificationBatchReview`` so the wizard shell and the
 * Settings sheet import the same surface area.
 */

import { ClassificationBatchReview } from "@/components/onboarding/classification-batch-review"
import { postOnboardingBackfillChunk } from "@/lib/api"

export type StepClassificationProps = {
  source: string
  /**
   * After the user submits fixes we must tell the orchestrator to leave the
   * ``needs_classification`` gate — that is a dedicated POST body flag.
   */
  onContinueBackfill: () => void
}

export function StepClassification({ source, onContinueBackfill }: StepClassificationProps) {
  return (
    <ClassificationBatchReview
      source={source}
      onSubmitted={async () => {
        await postOnboardingBackfillChunk(source, { resume_after_classification: true })
        onContinueBackfill()
      }}
    />
  )
}
