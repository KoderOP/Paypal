import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type { AuthState } from '../lib/types'

/** Optional Sign in with PayPal. Nothing in the app is gated on it; it only personalises the UI. */
interface Ctx { auth: AuthState | null; refresh: () => Promise<void>; signOut: () => Promise<void> }
const AuthContext = createContext<Ctx>({ auth: null, refresh: async () => {}, signOut: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState | null>(null)
  const refresh = useCallback(async () => {
    try { setAuth(await api.me()) } catch { /* backend unreachable: DataStatus shows the error */ }
  }, [])
  const signOut = useCallback(async () => { await api.logout(); await refresh() }, [refresh])
  useEffect(() => { void refresh() }, [refresh])
  return <AuthContext.Provider value={{ auth, refresh, signOut }}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext)
