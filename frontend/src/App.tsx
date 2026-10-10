import { useState } from 'react'
import { login, getCurrentUser } from './api'
import './App.css'

function App() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [authenticatedUser, setAuthenticatedUser] = useState('')

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(username, password)

      const result = await getCurrentUser()
      setAuthenticatedUser(result.username)
      setPassword('')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to sign in. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  if (authenticatedUser) {
    return (
      <main className="login-page">
        <section className="login-card">
          <div className="login-brand">
            <h1>Entropy</h1>
            <p>Deployment Management Platform</p>
          </div>

          <div className="login-heading">
            <h2>Welcome, {authenticatedUser}</h2>
            <p>You have successfully signed in.</p>
          </div>

          <button
            className="login-button"
            type="button"
            onClick={() => window.location.reload()}
          >
            Continue
          </button>
        </section>
      </main>
    )
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-brand">
          <h1>Entropy</h1>
          <p>Deployment Management Platform</p>
        </div>

        <div className="login-heading">
          <h2>Welcome back</h2>
          <p>Sign in to continue to your workspace.</p>
        </div>

        <form onSubmit={handleLogin}>
          <div className="form-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              name="username"
              type="text"
              placeholder="Enter your username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              disabled={loading}
            />
          </div>

          <div className="form-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              placeholder="Enter your password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              disabled={loading}
            />
          </div>

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button
            className="login-button"
            type="submit"
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="login-footer">
          Secure access to your deployment workspace
        </p>
      </section>
    </main>
  )
}

export default App
