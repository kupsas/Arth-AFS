/**
 * React Query helpers for the Track 2 onboarding wizard (Phase 5).
 *
 * The FastAPI routes live under ``/api/onboarding/*``.  We keep query keys in one
 * place so both the full-screen ``/setup`` wizard and the Settings **Connect account**
 * sheet can invalidate the same cache after discovery / backfill / completion.
 */
"use client"

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query"

import {
  fetchOnboardingBackfillSources,
  fetchOnboardingClassifierStatus,
  fetchOnboardingState,
  patchOnboardingState,
  postOnboardingBackfillChunk,
  postOnboardingComplete,
  postOnboardingDiscover,
  SETUP_STATUS_QUERY_KEY,
} from "@/lib/api"
import type {
  OnboardingBackfillSourceRow,
  OnboardingStateResponse,
} from "@/lib/types"

export const onboardingStateKey = ["onboarding", "state"] as const
export const onboardingBackfillSourcesKey = ["onboarding", "backfill-sources"] as const
export const onboardingClassifierStatusKey = ["onboarding", "classifier-status"] as const

export function useOnboardingState(
  options?: Partial<UseQueryOptions<OnboardingStateResponse>>,
) {
  return useQuery<OnboardingStateResponse>({
    queryKey: [...onboardingStateKey],
    queryFn: () => fetchOnboardingState(),
    staleTime: 10_000,
    ...options,
  })
}

export function useOnboardingBackfillSources(
  options?: Partial<UseQueryOptions<OnboardingBackfillSourceRow[]>>,
) {
  return useQuery<OnboardingBackfillSourceRow[]>({
    queryKey: [...onboardingBackfillSourcesKey],
    queryFn: () => fetchOnboardingBackfillSources(),
    staleTime: 60_000,
    ...options,
  })
}

export function useOnboardingClassifierStatus(
  options?: Partial<
    UseQueryOptions<{
      llm_model: string
      has_any_api_key: boolean
      unknown_threshold: number
    }>
  >,
) {
  return useQuery({
    queryKey: [...onboardingClassifierStatusKey],
    queryFn: () => fetchOnboardingClassifierStatus(),
    staleTime: 30_000,
    ...options,
  })
}

export function usePatchOnboardingState() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: patchOnboardingState,
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...onboardingStateKey] }),
  })
}

export function useOnboardingDiscover() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: postOnboardingDiscover,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...onboardingStateKey] })
    },
  })
}

export function useOnboardingBackfillChunk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: {
      source: string
      body?: {
        chunk_size?: number
        resume_after_classification?: boolean
        resume_from_pause?: boolean
      }
    }) => postOnboardingBackfillChunk(args.source, args.body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...onboardingStateKey] })
    },
  })
}

export function useOnboardingComplete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: postOnboardingComplete,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...onboardingStateKey] })
      void qc.invalidateQueries({ queryKey: SETUP_STATUS_QUERY_KEY })
    },
  })
}
