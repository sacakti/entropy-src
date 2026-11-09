import { useCallback, useEffect, useState } from 'react'
import { ArrowRightLeft, CheckCircle2, LoaderCircle, Plug, Save } from 'lucide-react'

import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { apiRequest } from '../../services/api'
import { settingsApi, type ConnectionTestResult, type DatabaseTargetSettings } from '../../api/settings.api'
import { databaseSwitchDetail, databaseSwitchLabel, type DatabaseSwitch } from '../../api/vision.api'
import { VISION_REFRESH_EVENT } from '../vision/bus'

export interface EngineInfo {
    engine: string
    host?: string
    port?: number
    database?: string
    schema?: string
    username?: string
    ssl?: boolean
}

interface SwitchResult {
    engine: string
    switching: boolean
    restarting: boolean
}

const ENGINE_LABELS: Record<string, string> = { sqlite: 'SQLite', postgresql: 'PostgreSQL', oracle: 'Oracle' }
type ServerEngine = DatabaseTargetSettings['engine']
const DEFAULT_PORTS: Record<ServerEngine, number> = { postgresql: 5432, oracle: 1521 }
const FIELD_HINTS: Record<ServerEngine, { database: string; placeholder: string; schema: string; tls: string }> = {
    postgresql: {
        database: 'Database name',
        placeholder: 'entropy',
        schema: "Optional. Empty uses the user's default, usually public.",
        tls: 'Require TLS (sslmode=require)',
    },
    oracle: {
        database: 'Service name',
        placeholder: 'ORCLPDB1',
        schema: "Optional. An existing schema (Oracle user) the user can create tables in; empty uses the user's own.",
        tls: 'Use TLS (TCPS)',
    },
}

const serverEngine = (engine: string | undefined): ServerEngine => (engine === 'oracle' ? 'oracle' : 'postgresql')
const PROGRESS_URL = '/api/admin/database/switch'
const PROGRESS_POLL_MS = 1000

function message(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

const isUnderWay = (progress: DatabaseSwitch) => ['copying', 'restarting', 'restart_required'].includes(progress.state)

/**
 * Administration -> Settings -> Database: SQLite by default; PostgreSQL or Oracle when
 * an administrator switches to it, which copies the data once.
 */
export default function DatabaseEngine({ info }: { info: EngineInfo }) {
    const { notify, modal } = useFeedback()
    const [target, setTarget] = useState<DatabaseTargetSettings | null>(null)
    const [password, setPassword] = useState<string | null>(null)
    const [busy, setBusy] = useState<string | null>(null)
    const [test, setTest] = useState<ConnectionTestResult | null>(null)
    const [progress, setProgress] = useState<DatabaseSwitch | null>(null)
    const onSqlite = info.engine === 'sqlite'
    const underWay = progress !== null

    const follow = useCallback(async () => {
        const next = await apiRequest<DatabaseSwitch>(PROGRESS_URL)
        if (isUnderWay(next)) {
            setProgress(next)
        } else if (next.state === 'failed') {
            setProgress(null)
            notify.error(next.error || 'The switch failed. Entropy stays on SQLite.', { title: 'Database' })
            window.dispatchEvent(new Event(VISION_REFRESH_EVENT))
        } else if (next.state === 'idle') {
            // A new server knows of no switch: it has restarted on the new database.
            window.location.reload()
        }
    }, [notify])

    // A switch may have started before this page was opened.
    useEffect(() => {
        apiRequest<DatabaseSwitch>(PROGRESS_URL)
            .then((next) => {
                if (isUnderWay(next)) setProgress(next)
            })
            .catch(() => undefined)
    }, [])

    useEffect(() => {
        if (!underWay) return
        // A failed request is the server restarting: keep asking.
        const timer = window.setInterval(() => void follow().catch(() => undefined), PROGRESS_POLL_MS)
        return () => window.clearInterval(timer)
    }, [underWay, follow])

    useEffect(() => {
        if (!onSqlite) return
        settingsApi
            .all()
            .then((all) => setTarget({ ...all.database_target, engine: serverEngine(all.database_target.engine) }))
            .catch((cause: unknown) => notify.error(message(cause, 'Unable to load the connection.')))
    }, [onSqlite, notify])

    const run = async (key: string, action: () => Promise<void>) => {
        setBusy(key)
        try {
            await action()
        } catch (cause) {
            notify.error(message(cause, 'The action failed.'))
        } finally {
            setBusy(null)
        }
    }

    const update = (changes: Partial<DatabaseTargetSettings>) => {
        setTest(null)
        setTarget((current) => (current ? { ...current, ...changes } : current))
    }

    // The other engine's default port means nothing here; a port someone typed stays.
    const chooseEngine = (engine: ServerEngine) => {
        setTest(null)
        setTarget((current) => {
            if (!current || current.engine === engine) return current
            const port = current.port === DEFAULT_PORTS[current.engine] || !current.port ? DEFAULT_PORTS[engine] : current.port
            return { ...current, engine, port }
        })
    }

    const save = async () => {
        if (!target) return
        const saved = await settingsApi.save<DatabaseTargetSettings>('database_target', {
            ...target,
            enabled: true,
            password,
        })
        setTarget({ ...saved, engine: serverEngine(saved.engine) })
        setPassword(null)
    }

    const switchTo = async (engine: string) => {
        const result = await apiRequest<SwitchResult>('/api/admin/database/engine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ engine }),
        })
        if (result.switching) {
            await follow()
            window.dispatchEvent(new Event(VISION_REFRESH_EVENT))
            return
        }
        notify.success(
            result.restarting
                ? `Entropy is restarting on ${ENGINE_LABELS[result.engine]}.`
                : `Restart Entropy to run on ${ENGINE_LABELS[result.engine]}.`,
        )
        if (result.restarting) window.setTimeout(() => window.location.reload(), 5000)
    }

    const confirmSwitch = async (engine: string, text: string) => {
        const confirmed = await modal.confirm({
            title: `Switch to ${ENGINE_LABELS[engine]}?`,
            message: text,
            confirmText: 'Switch database',
        })
        if (confirmed) await run('switch', () => switchTo(engine))
    }

    if (!onSqlite) {
        return (
            <>
                <header className="settings-admin-head">
                    <div>
                        <h2>Database</h2>
                        <p>
                            Entropy runs on {ENGINE_LABELS[info.engine] ?? info.engine}. Back it up with your database
                            server's own tools: Entropy's file backups and recovery only protect SQLite.
                        </p>
                    </div>
                </header>
                <div className="database-cards">
                    <div className="database-card">
                        <CheckCircle2 size={18} aria-hidden="true" />
                        <div>
                            <strong>{info.database}</strong>
                            <code>
                                {info.host}:{info.port}
                                {info.schema ? ` · ${info.schema}` : ''}
                            </code>
                        </div>
                    </div>
                </div>
                <div className="database-actions">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        disabled={busy !== null}
                        aria-busy={busy === 'switch'}
                        onClick={() =>
                            void confirmSwitch(
                                'sqlite',
                                'Entropy goes back to its SQLite file as it was when you switched. Nothing is copied back: changes made since then stay in this database only.',
                            )
                        }
                    >
                        {busy === 'switch' ? <LoaderCircle size={15} className="entropy-spin" /> : <ArrowRightLeft size={15} />}
                        Switch back to SQLite
                    </button>
                </div>
            </>
        )
    }

    const engine = serverEngine(target?.engine)
    const hints = FIELD_HINTS[engine]

    return (
        <>
            <h3 className="database-subhead">Use PostgreSQL or Oracle instead</h3>
            <p className="settings-muted">
                For larger installations. Give Entropy an empty database (Oracle: an empty schema, Oracle 19c or later):
                switching copies all data once and restarts the server on it. The SQLite file stays as it is.
            </p>
            {target && (
                <>
                    <div className="settings-grid">
                        <label className="admin-field admin-field-wide">
                            <span>Database engine</span>
                            <select
                                className="entropy-select"
                                value={engine}
                                disabled={underWay}
                                onChange={(event) => chooseEngine(event.target.value as ServerEngine)}
                            >
                                <option value="postgresql">PostgreSQL</option>
                                <option value="oracle">Oracle Database (19c or later)</option>
                            </select>
                        </label>
                        <label className="admin-field">
                            <span>Host</span>
                            <input value={target.host} spellCheck={false} onChange={(event) => update({ host: event.target.value })} />
                        </label>
                        <label className="admin-field">
                            <span>Port</span>
                            <input
                                type="number"
                                min={1}
                                max={65535}
                                value={target.port}
                                onChange={(event) => update({ port: Number(event.target.value) })}
                            />
                        </label>
                        <label className="admin-field">
                            <span>{hints.database}</span>
                            <input
                                value={target.database}
                                spellCheck={false}
                                placeholder={hints.placeholder}
                                onChange={(event) => update({ database: event.target.value })}
                            />
                        </label>
                        <label className="admin-field">
                            <span>Schema</span>
                            <input value={target.schema} spellCheck={false} onChange={(event) => update({ schema: event.target.value })} />
                            <small>{hints.schema}</small>
                        </label>
                        <label className="admin-field">
                            <span>User name</span>
                            <input value={target.username} autoComplete="off" onChange={(event) => update({ username: event.target.value })} />
                        </label>
                        <label className="admin-field">
                            <span>Password</span>
                            <input
                                type="password"
                                autoComplete="new-password"
                                value={password ?? ''}
                                placeholder={target.password_set ? 'Saved; type to change' : ''}
                                onChange={(event) => {
                                    setTest(null)
                                    setPassword(event.target.value)
                                }}
                            />
                        </label>
                        <label className="admin-field admin-field-wide">
                            <span>
                                <input type="checkbox" checked={target.ssl} onChange={(event) => update({ ssl: event.target.checked })} />{' '}
                                {hints.tls}
                            </span>
                        </label>
                    </div>
                    {test && (
                        <div className="settings-connection-result" role="status">
                            <CheckCircle2 size={16} aria-hidden="true" />
                            <span>
                                {test.summary} {test.details.join(' ')}
                            </span>
                        </div>
                    )}
                    {progress && (
                        <div className="database-switch" role="status">
                            <strong>{databaseSwitchLabel(progress)}</strong>
                            <progress
                                max={Math.max(progress.rows_total, 1)}
                                value={progress.state === 'copying' ? progress.rows_done : progress.rows_total}
                                aria-label="Rows copied"
                            />
                            <small>
                                {progress.rows_total > 0 && `${progress.rows_done} of ${progress.rows_total} rows. `}
                                {databaseSwitchDetail(progress)}
                            </small>
                        </div>
                    )}
                    <div className="database-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            disabled={busy !== null || underWay}
                            aria-busy={busy === 'test'}
                            onClick={() =>
                                void run('test', async () => {
                                    await save()
                                    setTest(await settingsApi.testConnection('database_target'))
                                })
                            }
                        >
                            {busy === 'test' ? <LoaderCircle size={15} className="entropy-spin" /> : <Plug size={15} />}
                            Save and test
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            disabled={busy !== null || underWay}
                            aria-busy={busy === 'save'}
                            onClick={() => void run('save', save)}
                        >
                            {busy === 'save' ? <LoaderCircle size={15} className="entropy-spin" /> : <Save size={15} />}
                            Save
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            disabled={busy !== null || underWay || !test}
                            aria-busy={busy === 'switch' || underWay}
                            title={test || underWay ? undefined : 'Test the connection first.'}
                            onClick={() =>
                                void confirmSwitch(
                                    engine,
                                    `All data is copied to ${target.database} on ${target.host}, then the server restarts and everyone reconnects. Active runs must have finished. SQLite stays read-only during the copy, and changes after the switch are not copied back.`,
                                )
                            }
                        >
                            {busy === 'switch' || underWay ? <LoaderCircle size={15} className="entropy-spin" /> : <ArrowRightLeft size={15} />}
                            {underWay ? 'Switching…' : `Switch to ${ENGINE_LABELS[engine]}`}
                        </button>
                    </div>
                </>
            )}
        </>
    )
}
