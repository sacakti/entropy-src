import { useCallback, useEffect, useMemo, useState } from 'react'
import { LoaderCircle, Package, Plus, RefreshCw, Search, ShieldCheck, Trash2, Wrench, X } from 'lucide-react'

import { extensionsApi, type BuiltinLibrary, type ExtensionVersion } from '../../api/extensions.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { Tabs } from '../administration/AdminPanel'
import { missingPermission } from '../administration/permissionReason'
import { usePermissions } from '../administration/usePermissions'
import { errorMessage, formatDateTime } from '../runs/format'
import InstallExtensionDialog from './InstallExtensionDialog'
import '../../styles/extensions.css'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

function size(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const SOURCES: Record<ExtensionVersion['source'], string> = {
    index: 'Package index',
    upload: 'Uploaded',
    server: 'From the server',
}

/**
 * Extensions: Python libraries plugins need — from the package index or
 * your own — kept per version. A plugin lists them under "dependencies" in
 * its plugin.json; Entropy's own libraries count when the version fits.
 */
export default function Extensions() {
    const { notify, modal } = useFeedback()
    const permissions = usePermissions()
    const installReason = missingPermission(permissions, ['extensions.install'], 'Installing and removing libraries')

    const [installed, setInstalled] = useState<ExtensionVersion[]>([])
    const [builtin, setBuiltin] = useState<BuiltinLibrary[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [tab, setTab] = useState<'installed' | 'builtin'>('installed')
    const [search, setSearch] = useState('')
    const [installing, setInstalling] = useState(false)
    const [busy, setBusy] = useState<string | null>(null)

    const load = useCallback(async () => {
        try {
            const result = await extensionsApi.list()
            setInstalled(result.installed)
            setBuiltin(result.builtin)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Extensions could not be loaded.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        let active = true
        extensionsApi
            .list()
            .then((result) => {
                if (!active) return
                setInstalled(result.installed)
                setBuiltin(result.builtin)
            })
            .catch((cause) => {
                if (active) setError(errorMessage(cause, 'Extensions could not be loaded.'))
            })
            .finally(() => {
                if (active) setLoading(false)
            })
        return () => {
            active = false
        }
    }, [])

    const query = search.trim().toLowerCase()
    const shownInstalled = useMemo(
        () =>
            installed.filter(
                (entry) =>
                    !query ||
                    entry.name.toLowerCase().includes(query) ||
                    entry.summary.toLowerCase().includes(query) ||
                    entry.used_by.some((plugin) => plugin.toLowerCase().includes(query)),
            ),
        [installed, query],
    )
    const shownBuiltin = useMemo(
        () => builtin.filter((entry) => !query || entry.name.toLowerCase().includes(query) || entry.summary.toLowerCase().includes(query)),
        [builtin, query],
    )
    const libraries = new Set(installed.map((entry) => entry.canonical)).size

    const act = async (entry: ExtensionVersion, action: 'verify' | 'repair' | 'remove') => {
        const label = `${entry.name} ${entry.version}`
        if (action === 'remove') {
            const confirmed = await modal.confirm({
                title: `Remove ${label}?`,
                message: entry.used_by.length
                    ? `It is used by ${entry.used_by.join(', ')}. Removal is refused while they have no other version that fits.`
                    : 'Its files and kept wheels are deleted. Plugins that need it cannot be installed until it is back.',
                confirmText: 'Remove',
                destructive: true,
            })
            if (!confirmed) return
        }
        setBusy(`${entry.id}:${action}`)
        try {
            if (action === 'verify') {
                const { problems } = await extensionsApi.verify(entry.name, entry.version)
                if (problems.length) notify.error(`${label}: ${problems.join(' ')}`)
                else notify.success(`${label} is complete.`)
            } else if (action === 'repair') {
                await extensionsApi.repair(entry.name, entry.version)
                notify.success(`${label} was reinstalled from its wheels.`)
            } else {
                await extensionsApi.remove(entry.name, entry.version)
                notify.success(`${label} removed.`)
                await load()
            }
        } catch (cause) {
            notify.error(errorMessage(cause, `${label}: the action failed.`))
        } finally {
            setBusy(null)
        }
    }

    return (
        <section className="list-page extensions-page">

            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Extensions
                            <span className="list-count">{installed.length}</span>
                        </h2>
                        <p>
                            Python libraries for plugins: {libraries} librar{libraries === 1 ? 'y' : 'ies'} in {installed.length} version
                            {installed.length === 1 ? '' : 's'} · {builtin.length} built into Entropy
                        </p>
                    </div>
                    <div className="entropy-panel-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh extensions"
                            title="Refresh"
                            onClick={() => {
                                setRefreshing(true)
                                void load()
                            }}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon"
                            aria-label="Install a library"
                            title={installReason ?? 'Install a library'}
                            disabled={Boolean(installReason)}
                            onClick={() => setInstalling(true)}
                        >
                            <Plus size={20} />
                        </button>
                    </div>
                </div>

                <Tabs
                    tabs={[
                        { id: 'installed', label: 'Installed', count: installed.length },
                        { id: 'builtin', label: 'In Entropy', count: builtin.length },
                    ]}
                    active={tab}
                    onChange={setTab}
                />

                <div className="list-toolbar">
                    <div className="list-search">
                        <Search size={17} aria-hidden="true" />
                        <input
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder={tab === 'installed' ? 'Search libraries or plugins…' : 'Search Entropy’s libraries…'}
                            aria-label="Search libraries"
                        />
                        {search && (
                            <button type="button" aria-label="Clear search" onClick={() => setSearch('')}>
                                <X size={15} />
                            </button>
                        )}
                    </div>
                </div>

                {tab === 'installed' ? (
                    <div className="list-table-wrap">
                        <table className="list-table extensions-table">
                            <thead>
                                <tr>
                                    <th scope="col">Library</th>
                                    <th scope="col">Version</th>
                                    <th scope="col">Includes</th>
                                    <th scope="col">Used by</th>
                                    <th scope="col">Installed</th>
                                    <th scope="col" className="list-operations-cell">
                                        <span className="list-operations-heading">Operations</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading ? (
                                    <tr>
                                        <td colSpan={6}>
                                            <EntropyLoader label={`Loading extensions…`} />
                                        </td>
                                    </tr>
                                ) : shownInstalled.length === 0 ? (
                                    <tr>
                                        <td colSpan={6}>
                                            <div className="list-empty">
                                                <Package size={20} aria-hidden="true" />
                                                <strong>{query ? 'Nothing matches.' : 'No libraries installed yet.'}</strong>
                                                <span>
                                                    {query
                                                        ? 'Try a different search.'
                                                        : 'Install the libraries your plugins need with the + button. Entropy’s own libraries are under “In Entropy”.'}
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    shownInstalled.map((entry) => (
                                        <tr key={entry.id}>
                                            <td>
                                                <div className="runs-who">
                                                    <strong>{entry.name}</strong>
                                                    <span>{entry.summary || '—'}</span>
                                                </div>
                                            </td>
                                            <td>
                                                <code className="extension-version">{entry.version}</code>
                                            </td>
                                            <td className="list-cell-text">
                                                <span className="extension-packages" title={entry.packages.join('\n')}>
                                                    {entry.packages.length <= 1
                                                        ? 'Just itself'
                                                        : `${entry.packages.length - 1} dependenc${entry.packages.length === 2 ? 'y' : 'ies'}`}
                                                    {entry.shared.length > 0 && ` · shares ${entry.shared.length} with Entropy`}
                                                </span>
                                                <small>{size(entry.size)}</small>
                                            </td>
                                            <td className="list-cell-text">
                                                {entry.used_by.length ? (
                                                    <span className="extension-users">{entry.used_by.join(', ')}</span>
                                                ) : (
                                                    <span className="eagle-muted">No plugin yet</span>
                                                )}
                                            </td>
                                            <td className="list-cell-text">
                                                <span>{formatDateTime(entry.installed_at)}</span>
                                                <small>
                                                    {SOURCES[entry.source]}
                                                    {entry.origin && entry.source !== 'server' ? ` · ${entry.origin}` : ''}
                                                    {entry.installed_by ? ` · ${entry.installed_by}` : ''}
                                                </small>
                                            </td>
                                            <td className="list-operations-cell">
                                                <div className="list-operations">
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`Verify ${entry.name} ${entry.version}`}
                                                        title="Verify its files"
                                                        disabled={busy !== null}
                                                        onClick={() => void act(entry, 'verify')}
                                                    >
                                                        {busy === `${entry.id}:verify` ? <LoaderCircle size={15} className="entropy-spin" /> : <ShieldCheck size={15} />}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`Repair ${entry.name} ${entry.version}`}
                                                        title={installReason ?? 'Reinstall from its kept wheels'}
                                                        disabled={busy !== null || Boolean(installReason)}
                                                        onClick={() => void act(entry, 'repair')}
                                                    >
                                                        {busy === `${entry.id}:repair` ? <LoaderCircle size={15} className="entropy-spin" /> : <Wrench size={15} />}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                        aria-label={`Remove ${entry.name} ${entry.version}`}
                                                        title={installReason ?? 'Remove this version'}
                                                        disabled={busy !== null || Boolean(installReason)}
                                                        onClick={() => void act(entry, 'remove')}
                                                    >
                                                        {busy === `${entry.id}:remove` ? <LoaderCircle size={15} className="entropy-spin" /> : <Trash2 size={15} />}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="list-table-wrap">
                        <p className="extension-note">
                            Entropy runs with these libraries. A plugin that needs one of them at a fitting version uses it as it is; for
                            another version, install that version under Installed.
                        </p>
                        <table className="list-table extensions-table">
                            <thead>
                                <tr>
                                    <th scope="col">Library</th>
                                    <th scope="col">Version</th>
                                </tr>
                            </thead>
                            <tbody>
                                {shownBuiltin.map((entry) => (
                                    <tr key={entry.name}>
                                        <td>
                                            <div className="runs-who">
                                                <strong>{entry.name}</strong>
                                                <span>{entry.summary || '—'}</span>
                                            </div>
                                        </td>
                                        <td>
                                            <code className="extension-version">{entry.version}</code>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            {installing && (
                <InstallExtensionDialog
                    builtin={builtin}
                    installed={installed}
                    onInstalled={(extension) => {
                        notify.success(`${extension.name} ${extension.version} installed.`)
                        setTab('installed')
                        void load()
                    }}
                    onClose={() => setInstalling(false)}
                />
            )}
        </section>
    )
}
