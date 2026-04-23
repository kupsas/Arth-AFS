/**
 * GET /api/metrics/classification-stats — coarse rules / LLM / user / unclassified mix.
 */
"use client"

import { useQuery, type UseQueryOptions } from "@tanstack/react-query"

import { fetchClassificationStats } from "@/lib/api"
import type { ClassificationStatsResponse } from "@/lib/types"

export const classificationStatsKey = ["metrics", "classification-stats"] as const

export function useClassificationStats(
  options?: Partial<UseQueryOptions<ClassificationStatsResponse>>,
) {
  return useQuery<ClassificationStatsResponse>({
    queryKey: [...classificationStatsKey],
    queryFn: () => fetchClassificationStats(),
    staleTime: 60_000,
    ...options,
  })
}
