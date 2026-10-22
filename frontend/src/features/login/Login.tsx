import { useEffect, useRef, useState, type FormEvent } from 'react'
import './login.css'

interface Providers {
  ldap: boolean
  oidc: { enabled: boolean; label: string }
}

/** A single sign-on failure the server sent back as ?sso_error=..., once. */
function takeSsoError(): string {
  const params = new URLSearchParams(window.location.search)
  const message = params.get('sso_error') ?? ''
  if (message) {
    params.delete('sso_error')
    const query = params.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`)
  }
  return message
}

export interface EndedSession {
  name: string
  username: string
  reason: 'signed-out' | 'expired'
}

type LoginProps = {
  onLogin: (username: string, password: string) => Promise<void>
  endedSession?: EndedSession | null
}

export default function Login({ onLogin, endedSession }: LoginProps) {
  const [username, setUsername] = useState(endedSession?.username ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(takeSsoError)
  const [loading, setLoading] = useState(false)
  const [providers, setProviders] = useState<Providers | null>(null)
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => {
    fetch('/api/auth/providers', { credentials: 'same-origin' })
      .then((response) => (response.ok ? response.json() : null))
      .then((value: Providers | null) => setProviders(value))
      .catch(() => setProviders(null))
  }, [])

  // Enter signs in even when no field has focus, e.g. after the browser's
  // password manager filled both fields.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Enter' || event.defaultPrevented) return
      const form = formRef.current
      if (!form || form.contains(document.activeElement)) return
      event.preventDefault()
      form.requestSubmit()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await onLogin(username, password)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-page">
      {/* Entropy's mark, large and faded, behind the sign-in card. */}
      <div className="login-backdrop" aria-hidden="true">
        <img src="/entropy-logo.svg" alt="" />
      </div>
      <section className="login-card">
        <div className="login-brand">
          <div className="login-brand-heading"><img className="entropy-logo" src="/entropy-logo.svg" alt="Entropy logo" /><h1>Entropy</h1></div>
          <p>Deployment Management Platform</p>
        </div>
        <div className="login-heading"><h2>Welcome back</h2><p>Sign in to continue to your workspace.</p></div>
        {endedSession && (
          <p className="login-session-ended" role="status">
            {endedSession.reason === 'expired'
              ? <>Your session ended, <strong>{endedSession.name}</strong>. Sign in again to continue.</>
              : <><strong>{endedSession.name}</strong> signed out.</>}
          </p>
        )}
        <form ref={formRef} onSubmit={handleSubmit}>
          {providers?.ldap && <p className="login-hint">Use your directory (LDAP) account or your Entropy account.</p>}
          <div className="form-field"><label htmlFor="username">Username</label><input id="username" name="username" type="text" placeholder="Enter your username" autoComplete="username" autoFocus={!endedSession?.username} value={username} onChange={(event) => setUsername(event.target.value)} required disabled={loading} /></div>
          <div className="form-field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" placeholder="Enter your password" autoComplete="current-password" autoFocus={Boolean(endedSession?.username)} value={password} onChange={(event) => setPassword(event.target.value)} required disabled={loading} /></div>
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="entropy-button entropy-button-primary entropy-button-block login-button" type="submit" disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</button>
        </form>
        {providers?.oidc.enabled && (
          <>
            <div className="login-divider" aria-hidden="true"><span>or</span></div>
            <a className="entropy-button entropy-button-secondary entropy-button-block login-sso" href="/api/auth/oidc/start">
              {providers.oidc.label}
            </a>
          </>
        )}
      </section>
    </main>
  )
}
