import { useState, type FormEvent } from 'react'
import './login.css'

export interface EndedSession {
  name: string
  username: string
  reason: 'signed-out' | 'expired'
}

type LoginProps = {
  onLogin: (username: string, password: string) => Promise<void>
  endedSession?: EndedSession | null
}

function LoginIntro() {
  return (
    <aside className="login-intro">
      <div className="intro-content">
        <p className="intro-eyebrow">Engineering · Automation · Infrastructure</p>
        <h2>Build what matters.<br /><span>Run it beautifully.</span></h2>
        <p className="intro-description">
          Entropy brings deployment workflows, plugins, and operational automation together in one place. Build repeatable processes, manage execution, and keep your infrastructure work organized.
        </p>
        <div className="intro-principles">
          <article className="intro-principle"><h3>Automate the obvious.</h3><p>Turn repeatable deployment tasks into consistent workflows.</p></article>
          <article className="intro-principle"><h3>Design for reliability.</h3><p>Make execution easier to manage, inspect, and understand.</p></article>
          <article className="intro-principle"><h3>Keep complexity in check.</h3><p>Bring your deployment tools together in a clear workspace.</p></article>
        </div>
        <p className="intro-bottom">ENTROPY · DEPLOYMENT MANAGEMENT PLATFORM</p>
      </div>
    </aside>
  )
}

export default function Login({ onLogin, endedSession }: LoginProps) {
  const [username, setUsername] = useState(endedSession?.username ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

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
      <LoginIntro />
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
        <form onSubmit={handleSubmit}>
          <div className="form-field"><label htmlFor="username">Username</label><input id="username" name="username" type="text" placeholder="Enter your username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required disabled={loading} /></div>
          <div className="form-field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" placeholder="Enter your password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required disabled={loading} /></div>
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="entropy-button entropy-button-primary entropy-button-block login-button" type="submit" disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</button>
        </form>
        <p className="login-footer">Secure access to your deployment workspace</p>
      </section>
    </main>
  )
}
