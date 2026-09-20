import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, clearToken, getToken, setToken } from '../lib/api'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(getToken()))

  // Re-hydrate the session on a hard refresh: the token lives in localStorage,
  // the user record comes back from /api/auth/me.
  useEffect(() => {
    if (!getToken()) return
    let cancelled = false
    api
      .me()
      .then((data) => {
        if (!cancelled) setUser(data.user)
      })
      .catch(() => clearToken())
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const adopt = useCallback((data) => {
    setToken(data.token)
    setUser(data.user)
  }, [])

  const login = useCallback(
    async (credentials) => adopt(await api.login(credentials)),
    [adopt],
  )

  const register = useCallback(
    async (details) => adopt(await api.register(details)),
    [adopt],
  )

  const logout = useCallback(async () => {
    // Tell the server to revoke the token first, but never block signing out
    // locally on that request succeeding.
    try {
      await api.logout()
    } catch {
      /* offline or already expired — clearing locally is still correct */
    }
    clearToken()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
