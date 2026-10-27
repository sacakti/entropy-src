import { useEffect, useRef, useState, type FormEvent } from 'react'
import './login.css'
import { useErrorToast } from '../../components/feedback/useToast'

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
  useErrorToast(error)
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
      {/* Entropy's mark, very large and in the background's own olive tone. */}
      <div className="login-backdrop" aria-hidden="true">
        <svg viewBox="0 0 64 64" focusable="false">
          <rect x="2" y="2" width="60" height="60" rx="14" fill="currentColor" fillOpacity="0.35" stroke="currentColor" strokeWidth="1" />
          <g fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
            <rect x="19" y="17" width="12" height="12" rx="3" />
            <path d="M31 23h6a4 4 0 0 1 4 4v6" />
            <rect x="35" y="33" width="12" height="12" rx="3" />
            <path d="M29 29v7a4 4 0 0 0 4 4h2" />
          </g>
        </svg>
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
