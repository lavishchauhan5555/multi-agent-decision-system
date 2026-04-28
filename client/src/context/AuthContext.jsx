// context/AuthContext.jsx
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'

const AuthContext = createContext(null)
const API = import.meta.env.VITE_API_URL || 'https://multi-agent-decision-system.onrender.com'

function parseJwt(token) {
  try { return JSON.parse(atob(token.split('.')[1])) } catch { return null }
}
function msUntilExpiry(token) {
  const p = parseJwt(token)
  if (!p?.exp) return -1
  return p.exp * 1000 - Date.now()
}

// Module-level — one shared promise across StrictMode double-mounts
let globalRefreshPromise = null

async function callRefresh() {
  if (globalRefreshPromise) return globalRefreshPromise
  globalRefreshPromise = fetch(`${API}/api/auth/refresh`, {
    method:      'POST',
    credentials: 'include',
    headers:     { 'Content-Type': 'application/json' },
  })
    .then(async r => {
      // 503 = DB/server temporarily down — throw so caller can retry, not logout
      if (r.status === 503) throw new Error('server_unavailable')
      const data = await r.json()
      return data?.accessToken ? data : null
    })
    .catch(err => {
      if (err.message === 'server_unavailable') throw err
      return null   // network error = treat as logged out
    })
    .finally(() => { globalRefreshPromise = null })
  return globalRefreshPromise
}

export function AuthProvider({ children }) {
  const [user,        setUser]        = useState(null)
  const [accessToken, setAccessToken] = useState(null)
  const [loading,     setLoading]     = useState(true)

  const timerRef    = useRef(null)
  const pingRef     = useRef(null)
  const initialised = useRef(false)

  const applySession = useCallback((data) => {
    if (data?.accessToken && data?.user) {
      setAccessToken(data.accessToken)
      setUser(data.user)
      // Schedule silent refresh 2 min before access token expires
      clearTimeout(timerRef.current)
      const delay = msUntilExpiry(data.accessToken) - 2 * 60 * 1000
      timerRef.current = setTimeout(async () => {
        try {
          const next = await callRefresh()
          applySession(next)
        } catch {
          // 503: server temporarily down — retry in 30s, don't log out
          timerRef.current = setTimeout(async () => {
            const next = await callRefresh().catch(() => null)
            applySession(next)
          }, 30_000)
        }
      }, Math.max(delay, 30_000))
    } else {
      setAccessToken(null)
      setUser(null)
    }
  }, [])

  // On mount: restore session from cookie ONCE
  useEffect(() => {
    if (initialised.current) return
    initialised.current = true

    callRefresh()
      .then(applySession)
      .catch(() => {
        // Server unavailable on page load — don't log out, just show loading=false
        // user will retry naturally
      })
      .finally(() => setLoading(false))

    // Keep-alive ping every 10 min while tab is visible
    pingRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') {
        callRefresh().then(applySession).catch(() => {})
      }
    }, 10 * 60 * 1000)

    return () => {
      clearTimeout(timerRef.current)
      clearInterval(pingRef.current)
    }
  }, [])

  // authFetch: injects Bearer token, retries once on 401 TOKEN_EXPIRED
  const authFetch = useCallback(async (url, opts = {}) => {
    const makeReq = (token) => fetch(`${API}${url}`, {
      ...opts,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...opts.headers,
      },
    })

    let res = await makeReq(accessToken)

    if (res.status === 401) {
      const body = await res.json().catch(() => ({}))
      if (body.code === 'TOKEN_EXPIRED' || body.error?.includes('expired')) {
        const data = await callRefresh().catch(() => null)
        if (data?.accessToken) {
          applySession(data)
          res = await makeReq(data.accessToken)
        } else {
          setUser(null)
          setAccessToken(null)
          throw new Error('Session expired — please log in again')
        }
      }
    }
    return res
  }, [accessToken, applySession])

  const login = useCallback(async (email, password) => {
    const res  = await fetch(`${API}/api/auth/login`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'Login failed')
    applySession(data)
    return data
  }, [applySession])

  const signup = useCallback(async (email, password, name) => {
    const res  = await fetch(`${API}/api/auth/signup`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'Signup failed')
    applySession(data)
    return data
  }, [applySession])

  const logout = useCallback(async () => {
    clearTimeout(timerRef.current)
    clearInterval(pingRef.current)
    await fetch(`${API}/api/auth/logout`, {
      method: 'POST', credentials: 'include',
    }).catch(() => {})
    setUser(null)
    setAccessToken(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, accessToken, loading, login, signup, logout, authFetch }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}