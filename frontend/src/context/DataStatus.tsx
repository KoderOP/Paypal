import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type { StatusData } from '../lib/types'

interface Ctx { status: StatusData | null; error: string | null; refresh: () => Promise<StatusData | null> }
const DataStatusContext = createContext<Ctx>({ status: null, error: null, refresh: async () => null })

export function DataStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StatusData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    try {
      const s = await api.status()
      setStatus(s)
      setError(null)
      return s
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return null
    }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  return <DataStatusContext.Provider value={{ status, error, refresh }}>{children}</DataStatusContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useDataStatus = () => useContext(DataStatusContext)
