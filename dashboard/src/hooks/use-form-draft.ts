"use client"

/**
 * Persist form state to localStorage so a refresh / brief disconnect does not wipe in-progress
 * onboarding fields. Debounced writes avoid hammering storage on every keystroke.
 *
 * **Security:** Do not use for secrets (API keys, passwords) — prefer server-only storage.
 */

import * as React from "react"

const DEBOUNCE_MS = 500

export type UseFormDraftResult<T> = {
  /** Current draft value (starts from localStorage merge + default, then live edits). */
  value: T
  setValue: React.Dispatch<React.SetStateAction<T>>
  /** Call after a successful server save so the next visit does not resurrect stale drafts. */
  clearDraft: () => void
  /** True if we merged non-empty data from localStorage on first paint (skip redundant server fetch). */
  restoredFromLocalStorage: boolean
}

function readStorage<T>(storageKey: string, defaultValue: T): { value: T; restored: boolean } {
  if (typeof window === "undefined") {
    return { value: defaultValue, restored: false }
  }
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (raw == null || raw === "") {
      return { value: defaultValue, restored: false }
    }
    const parsed = JSON.parse(raw) as unknown
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { value: defaultValue, restored: false }
    }
    return {
      value: { ...defaultValue, ...(parsed as Partial<T>) },
      restored: true,
    }
  } catch {
    return { value: defaultValue, restored: false }
  }
}

export function useFormDraft<T extends Record<string, unknown>>(
  storageKey: string,
  defaultValue: T,
): UseFormDraftResult<T> {
  const defaultRef = React.useRef(defaultValue)
  defaultRef.current = defaultValue

  const persistTimerRef = React.useRef<number | null>(null)

  const [{ value, restoredFromLocalStorage }, setBundle] = React.useState(() => {
    const { value: v, restored } = readStorage(storageKey, defaultRef.current)
    return { value: v, restoredFromLocalStorage: restored }
  })

  const setValue = React.useCallback<React.Dispatch<React.SetStateAction<T>>>((action) => {
    setBundle((prev) => {
      const next =
        typeof action === "function"
          ? (action as (p: T) => T)(prev.value)
          : action
      return { value: next, restoredFromLocalStorage: prev.restoredFromLocalStorage }
    })
  }, [])

  React.useEffect(() => {
    if (persistTimerRef.current) {
      window.clearTimeout(persistTimerRef.current)
      persistTimerRef.current = null
    }
    persistTimerRef.current = window.setTimeout(() => {
      persistTimerRef.current = null
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(value))
      } catch {
        // Quota / private mode — non-fatal.
      }
    }, DEBOUNCE_MS)
    return () => {
      if (persistTimerRef.current) {
        window.clearTimeout(persistTimerRef.current)
        persistTimerRef.current = null
      }
    }
  }, [storageKey, value])

  /** Remove persisted draft only — keeps current React state (so a successful save does not blank the UI). */
  const clearDraft = React.useCallback(() => {
    if (persistTimerRef.current) {
      window.clearTimeout(persistTimerRef.current)
      persistTimerRef.current = null
    }
    try {
      window.localStorage.removeItem(storageKey)
    } catch {
      /* ignore */
    }
  }, [storageKey])

  return { value, setValue, clearDraft, restoredFromLocalStorage }
}
