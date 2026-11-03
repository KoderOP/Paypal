import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../lib/api'

export interface ApiState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  reload: () => void
}

/** Fetches on mount and whenever `deps` change; exposes loading / error / reload. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fn()
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, loading, reload }
}
