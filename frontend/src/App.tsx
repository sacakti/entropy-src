import { useEffect, useState } from 'react'
import { login, getCurrentUser, logout } from './services/auth'
import EntropyShell from './EntropyShell'
import Login from './features/login/Login'

function App() {
  const [authenticatedUser, setAuthenticatedUser] = useState('')
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    let active = true
    async function restoreSession() {
      try {
        const result = await getCurrentUser()
        if (active) setAuthenticatedUser(result.user.username)
      } catch {
        if (active) setAuthenticatedUser('')
      } finally {
        if (active) setCheckingSession(false)
      }
    }
    void restoreSession()
    return () => { active = false }
  }, [])

  async function handleLogin(username: string, password: string) {
    await login(username, password)
    const result = await getCurrentUser()
    setAuthenticatedUser(result.user.username)
  }

  if (checkingSession) return <div className="session-loading">Loading Entropy...</div>

  if (authenticatedUser) {
    return <EntropyShell username={authenticatedUser} onLogout={async () => {
      try { await logout() } finally { setAuthenticatedUser(''); window.location.reload() }
    }} />
  }

  return <Login onLogin={handleLogin} />
}

export default App
