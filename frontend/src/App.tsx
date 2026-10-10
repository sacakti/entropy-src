import { useEffect, useState } from 'react'
import { login, getCurrentUser, logout } from './api'
import './App.css'
import EntropyShell from './EntropyShell'

function LoginIntro() {
    return (
        <aside className="login-intro">
            <div className="intro-content">
                <p className="intro-eyebrow">
                    Engineering · Automation · Infrastructure
                </p>

                <h2>
                    Build what matters.
                    <br />
                    <span>Run it beautifully.</span>
                </h2>

                <p className="intro-description">
                    Entropy brings deployment workflows, plugins, and operational
                    automation together in one place. Build repeatable processes,
                    manage execution, and keep your infrastructure work organized.
                </p>

                <div className="intro-principles">
                    <article className="intro-principle">
                        <h3>Automate the obvious.</h3>
                        <p>Turn repeatable deployment tasks into consistent workflows.</p>
                    </article>

                    <article className="intro-principle">
                        <h3>Design for reliability.</h3>
                        <p>Make execution easier to manage, inspect, and understand.</p>
                    </article>

                    <article className="intro-principle">
                        <h3>Keep complexity in check.</h3>
                        <p>Bring your deployment tools together in a clear workspace.</p>
                    </article>
                </div>

                <p className="intro-bottom">
                    ENTROPY · DEPLOYMENT MANAGEMENT PLATFORM
                </p>
            </div>
        </aside>
    )
}

function App() {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)
    const [authenticatedUser, setAuthenticatedUser] = useState('')

    const [checkingSession, setCheckingSession] = useState(true)

    useEffect(() => {
        let active = true

        async function restoreSession() {
            try {
                const result = await getCurrentUser()

                if (active) {
                    setAuthenticatedUser(result.user.username)
                }
            } catch {
                if (active) {
                    setAuthenticatedUser('')
                }
            } finally {
                if (active) {
                    setCheckingSession(false)
                }
            }
        }

        void restoreSession()

        return () => {
            active = false
        }
    }, [])

    async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError('')
        setLoading(true)

        try {
            await login(username, password)

            const result = await getCurrentUser()
            setAuthenticatedUser(result.user.username)
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

    if (checkingSession) {
        return <div className="session-loading">Loading Entropy...</div>
    }

    if (authenticatedUser) {
        return (
            <EntropyShell
                username={authenticatedUser}
                onLogout={async () => {
                    try {
                        await logout()
                    } finally {
                        setAuthenticatedUser('')
                        window.location.reload()
                    }
                }}
            />
        )
    }

    return (
        <main className="login-page">
            <LoginIntro />

            <section className="login-card">
                <div className="login-brand">
                    <div className="login-brand-heading">
                        <img
                            className="entropy-logo"
                            src="/entropy-logo.svg"
                            alt="Entropy logo"
                        />
                        <h1>Entropy</h1>
                    </div>
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

