import { useCallback, useEffect, useRef, useState } from 'react'
import { login, getCurrentUser, logout, type AuthUser } from './services/auth'
import { SESSION_EXPIRED_EVENT } from './services/api'
import EntropyShell from './EntropyShell'
import Login, { type EndedSession } from './features/login/Login'

// Survives the reload that follows sign-out, so the login page can say who left.
const ENDED_SESSION_KEY = 'entropy.ended-session'

function displayName(user: AuthUser): string {
  return user.full_name?.trim() || user.username
}

function readEndedSession(): EndedSession | null {
  try {
    const value = window.sessionStorage.getItem(ENDED_SESSION_KEY)
    return value ? (JSON.parse(value) as EndedSession) : null
  } catch {
    return null
  }
}

function rememberEndedSession(session: EndedSession) {
  try {
    window.sessionStorage.setItem(ENDED_SESSION_KEY, JSON.stringify(session))
  } catch {
    // Storage unavailable: the login page simply shows no notice.
  }
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [endedSession, setEndedSession] = useState<EndedSession | null>(readEndedSession)
  const [justSignedIn, setJustSignedIn] = useState(false)

  useEffect(() => {
    let active = true
    async function restoreSession() {
      try {
        const result = await getCurrentUser()
        if (active) setUser(result.user)
      } catch {
        if (active) setUser(null)
      } finally {
        if (active) setCheckingSession(false)
      }
    }
    void restoreSession()
    return () => { active = false }
  }, [])

  const userRef = useRef<AuthUser | null>(null)

  useEffect(() => {
    userRef.current = user
  }, [user])

  const endSession = useCallback((reason: EndedSession['reason']) => {
    const current = userRef.current

    if (!current) return

    const ended = { name: displayName(current), username: current.username, reason }
    rememberEndedSession(ended)
    setEndedSession(ended)
    setUser(null)
  }, [])

  // Any API call answered with 401 means the server-side session has ended.
  useEffect(() => {
    const handleExpired = () => endSession('expired')
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired)
  }, [endSession])

  async function handleLogin(username: string, password: string) {
    await login(username, password)
    const result = await getCurrentUser()
    try { window.sessionStorage.removeItem(ENDED_SESSION_KEY) } catch { /* ignore */ }
    setEndedSession(null)
    setJustSignedIn(true)
    setUser(result.user)
  }

  if (checkingSession) return <div className="session-loading">Loading Entropy...</div>

  if (user) {
    return <EntropyShell
      user={user}
      welcome={justSignedIn ? displayName(user) : null}
      onLogout={async () => {
        try { await logout() } finally {
          endSession('signed-out')
          // Start the next session from the dashboard, not the last page.
          window.history.replaceState(null, '', window.location.pathname + window.location.search)
          window.location.reload()
        }
      }}
    />
  }

  return <Login onLogin={handleLogin} endedSession={endedSession} />
}

export default App
