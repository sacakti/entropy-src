import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import {
    Activity,
    AlertCircle,
    ArrowDown,
    ArrowUp,
    ArrowUpDown,
    Check,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Copy,
    Filter,
    MoreHorizontal,
    LoaderCircle,
    Package,
    Pencil,
    Plus,
    RefreshCw,
    Search,
    Trash2,
    X,
} from 'lucide-react'

import {
    listPlugins,
    pluginsApi,
    type PluginItem,
    type PluginListParams,
} from '../../api/plugins.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import AppPortal from './AppPortal'
import CreatePluginModal from './CreatePluginModal'

// Monaco is large; load the editor only when a plugin is opened.
const PluginEditor = lazy(() => import('./editor/PluginEditor'))

type PluginStatusFilter = 'all' | 'enabled' | 'disabled'
type PluginSortField = NonNullable<PluginListParams['sort_by']>
type SortOrder = 'asc' | 'desc'

const PAGE_SIZE = 10

function formatDate(value: string | null): string {
    if (!value) return '—'

    const date = new Date(value)

    if (Number.isNaN(date.getTime())) return '—'

    return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(date)
}

function StatusBadge({ enabled }: { enabled: boolean }) {
    return (
        <span
            className={`plugins-status ${
                enabled ? 'plugins-status-enabled' : 'plugins-status-disabled'
            }`}
        >
            <span className="plugins-status-dot" />
            {enabled ? 'Enabled' : 'Disabled'}
        </span>
    )
}

function EmptyState({
    title,
    message,
}: {
    title: string
    message: string
}) {
    return (
        <div className="plugins-empty">
            <Package size={22} />
            <strong>{title}</strong>
            <p>{message}</p>
        </div>
    )
}

function SortButton({
    label,
    field,
    sortBy,
    order,
    onSort,
}: {
    label: string
    field: PluginSortField
    sortBy: PluginSortField
    order: SortOrder
    onSort: (field: PluginSortField) => void
}) {
    const active = sortBy === field

    return (
        <button
            type="button"
            className="plugins-sort"
            onClick={() => onSort(field)}
            aria-label={`Sort by ${label}`}
            aria-pressed={active}
        >
            {label}
            {active ? (
                order === 'asc' ? (
                    <ArrowUp size={14} />
                ) : (
                    <ArrowDown size={14} />
                )
            ) : (
                <ArrowUpDown size={14} />
            )}
        </button>
    )
}

function PluginRow({
    plugin,
    deleting,
    onCopy,
    onViewDetails,
    onEdit,
    onDelete,
}: {
    plugin: PluginItem
    deleting: boolean
    onCopy: (value: string) => void
    onViewDetails: (plugin: PluginItem) => void
    onEdit: (plugin: PluginItem) => void
    onDelete: (plugin: PluginItem) => void
}) {
    const [menuOpen, setMenuOpen] = useState(false)
    const menuRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!menuOpen) return

        function handlePointerDown(event: PointerEvent) {
            if (
                menuRef.current &&
                !menuRef.current.contains(event.target as Node)
            ) {
                setMenuOpen(false)
            }
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') setMenuOpen(false)
        }

        document.addEventListener('pointerdown', handlePointerDown)
        document.addEventListener('keydown', handleKeyDown)

        return () => {
            document.removeEventListener('pointerdown', handlePointerDown)
            document.removeEventListener('keydown', handleKeyDown)
        }
    }, [menuOpen])

    return (
        <tr>
            <td>
                <div className="plugins-name">
                    <span className="plugins-name-icon" aria-hidden="true">
                        <Package size={17} />
                    </span>
                    <div className="plugins-name-content">
                        <strong title={plugin.name}>{plugin.name}</strong>
                        <span title={plugin.qualified_name}>
                            {plugin.qualified_name}
                        </span>
                    </div>
                </div>
            </td>

            <td>
                <span className="plugins-cell-text" title={plugin.namespace}>
                    {plugin.namespace}
                </span>
            </td>

            <td>
                <span className="plugins-version">{plugin.version}</span>
            </td>

            <td>
                <StatusBadge enabled={plugin.enabled} />
            </td>

            <td>
                <span className="plugins-cell-text">
                    {formatDate(plugin.installed_at)}
                </span>
            </td>

            <td className="plugins-operations-cell">
                <div className="plugins-operations" ref={menuRef}>
                    <button
                        type="button"
                        className="plugins-operation-button"
                        aria-label={`Edit ${plugin.qualified_name}`}
                        title="Edit"
                        onClick={() => onEdit(plugin)}
                        disabled={deleting}
                    >
                        <Pencil size={15} />
                    </button>
                    <button
                        type="button"
                        className="plugins-operation-button plugins-operation-danger"
                        aria-label={`Delete ${plugin.qualified_name}`}
                        title="Delete"
                        onClick={() => onDelete(plugin)}
                        disabled={deleting}
                    >
                        {deleting ? (
                            <LoaderCircle size={15} className="plugins-spin" />
                        ) : (
                            <Trash2 size={15} />
                        )}
                    </button>
                    <button
                        type="button"
                        className="plugins-operation-trigger"
                        aria-label={`Operations for ${plugin.name}`}
                        aria-haspopup="menu"
                        aria-expanded={menuOpen}
                        onClick={() => setMenuOpen((open) => !open)}
                    >
                        <MoreHorizontal size={18} />
                        <ChevronDown size={13} />
                    </button>

                    {menuOpen && (
                        <div className="plugins-operation-menu" role="menu">
                            <button
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                    onViewDetails(plugin)
                                    setMenuOpen(false)
                                }}
                            >
                                <Activity size={15} />
                                View details
                            </button>

                            <button
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                    onCopy(plugin.qualified_name)
                                    setMenuOpen(false)
                                }}
                            >
                                <Copy size={15} />
                                Copy qualified name
                            </button>
                        </div>
                    )}
                </div>
            </td>
        </tr>
    )
}

export default function Plugins() {
    const [plugins, setPlugins] = useState<PluginItem[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const [searchInput, setSearchInput] = useState('')
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] =
        useState<PluginStatusFilter>('all')
    const [sortBy, setSortBy] = useState<PluginSortField>('name')
    const [order, setOrder] = useState<SortOrder>('asc')
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [totalPages, setTotalPages] = useState(0)

    const [selectedPlugin, setSelectedPlugin] =
        useState<PluginItem | null>(null)
    const [notice, setNotice] = useState<string | null>(null)
    const [summaryTotal, setSummaryTotal] = useState(0)
    const [createOpen, setCreateOpen] = useState(false)
    const [editingPlugin, setEditingPlugin] = useState<PluginItem | null>(null)
    const [deletingName, setDeletingName] = useState<string | null>(null)

    const { notify, modal } = useFeedback()

    const requestInProgress = useRef(false)
    const hasLoaded = useRef(false)

    const loadPlugins = useCallback(async () => {
        if (requestInProgress.current) return

        // `loading` starts true and only covers the first load.
        requestInProgress.current = true

        try {
            const result = await listPlugins({
                q: search || undefined,
                enabled:
                    statusFilter === 'all'
                        ? undefined
                        : statusFilter === 'enabled',
                sort_by: sortBy,
                order,
                page,
                page_size: PAGE_SIZE,
            })

            setPlugins(result.items)
            setSummaryTotal(result.summary.total)
            setTotal(result.pagination.total)
            setTotalPages(result.pagination.total_pages)
            setError(null)
            hasLoaded.current = true
        } catch {
            // Preserve existing data during transient background failures.
            setError('Unable to refresh plugin data.')
        } finally {
            setLoading(false)
            setRefreshing(false)
            requestInProgress.current = false
        }
    }, [search, statusFilter, sortBy, order, page])

    useEffect(() => {
        void loadPlugins()

        // Pause background polling while the editor is open.
        if (editingPlugin) return

        const timer = window.setInterval(() => {
            void loadPlugins()
        }, 5000)

        return () => window.clearInterval(timer)
    }, [loadPlugins, editingPlugin])

    const refreshPlugins = () => {
        setRefreshing(true)
        void loadPlugins()
    }

    const handleDelete = async (plugin: PluginItem) => {
        const confirmed = await modal.confirm({
            title: `Delete ${plugin.qualified_name}?`,
            message:
                'The plugin is uninstalled and its module directory is removed. ' +
                'Workflows that reference it will fail until it is installed again.',
            confirmText: 'Delete plugin',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setDeletingName(plugin.qualified_name)

        try {
            await pluginsApi.delete(plugin.qualified_name)
            notify.success(`${plugin.qualified_name} was deleted.`, {
                title: 'Plugin deleted',
            })

            if (plugins.length === 1 && page > 1) {
                setPage((current) => current - 1)
            } else {
                refreshPlugins()
            }
        } catch (cause) {
            notify.error(
                cause instanceof Error ? cause.message : 'Unable to delete plugin.',
                { title: 'Delete failed' },
            )
        } finally {
            setDeletingName(null)
        }
    }

    useEffect(() => {
        const timer = window.setTimeout(() => {
            setPage(1)
            setSearch(searchInput.trim())
        }, 300)

        return () => window.clearTimeout(timer)
    }, [searchInput])

    const handleSort = (field: PluginSortField) => {
        if (sortBy === field) {
            setOrder((current) => (current === 'asc' ? 'desc' : 'asc'))
        } else {
            setSortBy(field)
            setOrder('asc')
        }

        setPage(1)
    }

    const handleStatusFilter = (value: PluginStatusFilter) => {
        setStatusFilter(value)
        setPage(1)
    }

    const handleCopy = async (value: string) => {
        try {
            await navigator.clipboard.writeText(value)
            setNotice('Qualified name copied to clipboard.')
        } catch {
            setNotice('Unable to copy. Please copy the qualified name manually.')
        }
    }

    const clearFilters = () => {
        setSearchInput('')
        setSearch('')
        setStatusFilter('all')
        setSortBy('name')
        setOrder('asc')
        setPage(1)
    }

    const hasFilters = searchInput.trim() !== '' || statusFilter !== 'all'

    return (
        <section className="plugins-page">
            <header className="dashboard-heading">
                <div>
                    <p className="dashboard-eyebrow">DEPLOYMENT WORKSPACE</p>
                    <h1>Plugins</h1>
                    <p className="dashboard-subtitle">
                        Browse installed plugins and inspect their registration
                        and status.
                    </p>
                </div>

                <div className="plugins-heading-actions">
                    <button
                        type="button"
                        className="plugins-refresh"
                        onClick={refreshPlugins}
                        disabled={loading || refreshing}
                    >
                        <RefreshCw
                            size={16}
                            className={refreshing ? 'plugins-spin' : ''}
                        />
                        Refresh
                    </button>
                </div>
            </header>

            {error && (
                <div className="plugins-error" role="alert">
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button
                        type="button"
                        className="plugins-retry"
                        onClick={refreshPlugins}
                        disabled={refreshing}
                    >
                        Retry
                    </button>
                </div>
            )}

            {notice && (
                <div className="plugins-notice" role="status">
                    <Check size={16} />
                    <span>{notice}</span>
                    <button
                        type="button"
                        className="plugins-dismiss"
                        aria-label="Dismiss notification"
                        onClick={() => setNotice(null)}
                    >
                        <X size={15} />
                    </button>
                </div>
            )}

            <section className="dashboard-section plugins-section">
                <div className="dashboard-section-heading plugins-section-heading">
                    <div>
                        <h2>
                            Installed plugins
                            <span
                                className="plugins-count"
                                aria-label={`${summaryTotal} plugins in total`}
                            >
                                {summaryTotal.toLocaleString()}
                            </span>
                        </h2>
                        <p>
                            {total.toLocaleString()} plugin
                            {total === 1 ? '' : 's'}{' '}
                            {hasFilters ? 'match the current filters' : 'registered'}
                        </p>
                    </div>

                    <button
                        type="button"
                        className="plugins-create-button"
                        aria-label="Create plugin"
                        title="Create plugin"
                        onClick={() => setCreateOpen(true)}
                    >
                        <Plus size={20} />
                    </button>
                </div>

                <div className="plugins-toolbar">
                    <div className="plugins-search">
                        <Search size={17} aria-hidden="true" />
                        <input
                            type="search"
                            value={searchInput}
                            onChange={(event) =>
                                setSearchInput(event.target.value)
                            }
                            placeholder="Search plugins..."
                            aria-label="Search plugins"
                        />
                        {searchInput && (
                            <button
                                type="button"
                                aria-label="Clear search"
                                onClick={() => setSearchInput('')}
                            >
                                <X size={15} />
                            </button>
                        )}
                    </div>

                    <div className="plugins-toolbar-actions">
                        <label className="plugins-filter">
                            <Filter size={16} aria-hidden="true" />
                            <span>Status</span>
                            <select
                                value={statusFilter}
                                onChange={(event) =>
                                    handleStatusFilter(
                                        event.target.value as PluginStatusFilter,
                                    )
                                }
                                aria-label="Filter plugins by status"
                            >
                                <option value="all">All plugins</option>
                                <option value="enabled">Enabled</option>
                                <option value="disabled">Disabled</option>
                            </select>
                            <ChevronDown size={14} aria-hidden="true" />
                        </label>

                        {hasFilters && (
                            <button
                                type="button"
                                className="plugins-clear-filters"
                                onClick={clearFilters}
                            >
                                Clear filters
                            </button>
                        )}
                    </div>
                </div>

                <div className="plugins-table-wrap">
                    <table className="plugins-table">
                        <thead>
                            <tr>
                                <th scope="col">
                                    <SortButton
                                        label="Plugin"
                                        field="name"
                                        sortBy={sortBy}
                                        order={order}
                                        onSort={handleSort}
                                    />
                                </th>
                                <th scope="col">
                                    <SortButton
                                        label="Namespace"
                                        field="namespace"
                                        sortBy={sortBy}
                                        order={order}
                                        onSort={handleSort}
                                    />
                                </th>
                                <th scope="col">
                                    <SortButton
                                        label="Version"
                                        field="version"
                                        sortBy={sortBy}
                                        order={order}
                                        onSort={handleSort}
                                    />
                                </th>
                                <th scope="col">
                                    <SortButton
                                        label="Status"
                                        field="enabled"
                                        sortBy={sortBy}
                                        order={order}
                                        onSort={handleSort}
                                    />
                                </th>
                                <th scope="col">
                                    <SortButton
                                        label="Installed"
                                        field="installed_at"
                                        sortBy={sortBy}
                                        order={order}
                                        onSort={handleSort}
                                    />
                                </th>
                                <th scope="col">
                                    <span className="plugins-operations-heading">
                                        Operations
                                    </span>
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {loading && plugins.length === 0 ? (
                                <tr>
                                    <td colSpan={6}>
                                        <div
                                            className="plugins-loading"
                                            role="status"
                                        >
                                            <RefreshCw
                                                size={19}
                                                className="plugins-spin"
                                            />
                                            <span>Loading plugins…</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : plugins.length > 0 ? (
                                plugins.map((plugin) => (
                                    <PluginRow
                                        key={plugin.id}
                                        plugin={plugin}
                                        deleting={deletingName === plugin.qualified_name}
                                        onCopy={(value) => void handleCopy(value)}
                                        onViewDetails={setSelectedPlugin}
                                        onEdit={setEditingPlugin}
                                        onDelete={(item) => void handleDelete(item)}
                                    />
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={6}>
                                        <EmptyState
                                            title={
                                                error
                                                    ? 'Plugin list unavailable'
                                                    : 'No plugins found'
                                            }
                                            message={
                                                error
                                                    ? 'Retry the request to load the plugin list.'
                                                    : hasFilters
                                                      ? 'Try changing your search or status filter.'
                                                      : 'Installed plugins will appear here.'
                                            }
                                        />
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                <footer className="plugins-pagination">
                    <span>
                        {total === 0
                            ? 'No plugins'
                            : `Showing ${(page - 1) * PAGE_SIZE + 1}–${Math.min(
                                  page * PAGE_SIZE,
                                  total,
                              )} of ${total}`}
                    </span>

                    <div className="plugins-pagination-controls">
                        <label htmlFor="plugins-page-select">Page</label>
                        <select
                            id="plugins-page-select"
                            value={page}
                            onChange={(event) =>
                                setPage(Number(event.target.value))
                            }
                            disabled={totalPages <= 1}
                        >
                            {Array.from(
                                { length: totalPages },
                                (_, index) => index + 1,
                            ).map((pageNumber) => (
                                <option key={pageNumber} value={pageNumber}>
                                    {pageNumber}
                                </option>
                            ))}
                        </select>
                        <span>of {totalPages}</span>

                        <button
                            type="button"
                            className="plugins-page-arrow"
                            aria-label="Previous page"
                            disabled={page <= 1 || loading}
                            onClick={() => setPage((current) => current - 1)}
                        >
                            <ChevronLeft size={17} />
                        </button>
                        <button
                            type="button"
                            className="plugins-page-arrow"
                            aria-label="Next page"
                            disabled={page >= totalPages || loading}
                            onClick={() => setPage((current) => current + 1)}
                        >
                            <ChevronRight size={17} />
                        </button>
                    </div>
                </footer>
            </section>

            {selectedPlugin && (
                <AppPortal>
                    <div
                        className="plugins-modal-backdrop"
                        role="presentation"
                        onMouseDown={(event) => {
                            if (event.target === event.currentTarget) {
                                setSelectedPlugin(null)
                            }
                        }}
                    >
                        <section
                            className="plugins-details-modal"
                            role="dialog"
                            aria-modal="true"
                            aria-labelledby="plugins-details-title"
                        >
                            <header className="plugins-modal-heading">
                                <div>
                                    <p className="dashboard-eyebrow">
                                        PLUGIN DETAILS
                                    </p>
                                    <h2 id="plugins-details-title">
                                        {selectedPlugin.name}
                                    </h2>
                                </div>
                                <button
                                    type="button"
                                    className="plugins-dismiss"
                                    aria-label="Close plugin details"
                                    onClick={() => setSelectedPlugin(null)}
                                >
                                    <X size={18} />
                                </button>
                            </header>

                            <dl className="plugins-details-list">
                                <div>
                                    <dt>Qualified name</dt>
                                    <dd>{selectedPlugin.qualified_name}</dd>
                                </div>
                                <div>
                                    <dt>Namespace</dt>
                                    <dd>{selectedPlugin.namespace}</dd>
                                </div>
                                <div>
                                    <dt>Version</dt>
                                    <dd>{selectedPlugin.version}</dd>
                                </div>
                                <div>
                                    <dt>Status</dt>
                                    <dd>
                                        <StatusBadge
                                            enabled={selectedPlugin.enabled}
                                        />
                                    </dd>
                                </div>
                                <div>
                                    <dt>Installed at</dt>
                                    <dd>
                                        {formatDate(selectedPlugin.installed_at)}
                                    </dd>
                                </div>
                                <div>
                                    <dt>Registry ID</dt>
                                    <dd>{selectedPlugin.id}</dd>
                                </div>
                            </dl>

                            <footer className="plugins-modal-footer">
                                <button
                                    type="button"
                                    className="plugins-refresh"
                                    onClick={() => setSelectedPlugin(null)}
                                >
                                    Close
                                </button>
                            </footer>
                        </section>
                    </div>
                </AppPortal>
            )}

            {createOpen && (
                <AppPortal>
                    <CreatePluginModal
                        onClose={() => setCreateOpen(false)}
                        onCreated={(plugin) => {
                            setCreateOpen(false)
                            notify.success(
                                `${plugin.qualified_name} was created from the plugin template.`,
                                { title: 'Plugin created' },
                            )
                            refreshPlugins()
                            setEditingPlugin(plugin)
                        }}
                    />
                </AppPortal>
            )}

            {editingPlugin && (
                <AppPortal>
                    <Suspense
                        fallback={
                            <div className="plugins-modal-backdrop" role="status">
                                <LoaderCircle size={24} className="plugins-spin" />
                            </div>
                        }
                    >
                        <PluginEditor
                            key={editingPlugin.qualified_name}
                            plugin={editingPlugin}
                            onClose={() => setEditingPlugin(null)}
                            onSaved={() => {
                                setEditingPlugin(null)
                                refreshPlugins()
                            }}
                        />
                    </Suspense>
                </AppPortal>
            )}
        </section>
    )
}
