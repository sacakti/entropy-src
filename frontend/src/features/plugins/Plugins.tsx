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
    Download,
    MoreHorizontal,
    PackageCheck,
    Play,
    LoaderCircle,
    Package,
    Eye,
    Pencil,
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
import AddMenu from '../../components/layout/AddMenu'
import { missingPermission } from '../administration/permissionReason'
import { usePermissions } from '../administration/usePermissions'
import AppPortal from '../../components/layout/AppPortal'
import FloatingMenu from '../../components/layout/FloatingMenu'
import PickerDialog from '../../components/layout/PickerDialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import CreatePluginModal from './CreatePluginModal'
import StartRunDialog from '../runs/StartRunDialog'

// Monaco is large; load the editor only when a plugin is opened.
const PluginEditor = lazy(() => import('./editor/PluginEditor'))
const PluginHelp = lazy(() => import('./PluginHelp'))

type PluginStatusFilter = 'all' | 'enabled' | 'disabled' | 'draft'
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

function StatusBadge({ enabled, draft = false }: { enabled: boolean; draft?: boolean }) {
    return (
        <span
            className={`list-status ${
                draft ? 'list-status-draft' : enabled ? 'list-status-enabled' : 'list-status-disabled'
            }`}
            title={draft ? 'Saved but not installed; workflows cannot use it yet.' : undefined}
        >
            <span className="list-status-dot" />
            {draft ? 'Draft' : enabled ? 'Enabled' : 'Disabled'}
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
        <div className="list-empty">
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
            className="list-sort"
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
    selected,
    checked,
    onCheck,
    onRun,
    onInstall,
    onSelect,
    onCopy,
    onViewDetails,
    onEdit,
    onDelete,
    reasons,
    viewOnly,
}: {
    plugin: PluginItem
    /** Why each action is unavailable (null when allowed). */
    reasons: { run: string | null; install: string | null; edit: string | null; delete: string | null }
    /** The user may read the source but not change it. */
    viewOnly: boolean
    deleting: boolean
    selected: boolean
    checked: boolean
    onCheck: (plugin: PluginItem) => void
    onRun: (plugin: PluginItem) => void
    onInstall: (plugin: PluginItem) => void
    onSelect: (plugin: PluginItem) => void
    onCopy: (value: string) => void
    onViewDetails: (plugin: PluginItem) => void
    onEdit: (plugin: PluginItem) => void
    onDelete: (plugin: PluginItem) => void
}) {
    const [menuOpen, setMenuOpen] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)
    const closeMenu = useCallback(() => setMenuOpen(false), [])

    return (
        <tr
            className={selected ? 'is-selected' : undefined}
            aria-selected={selected}
            onClick={() => onSelect(plugin)}
        >
            <td className="list-check-cell" onClick={(event) => event.stopPropagation()}>
                <input
                    type="checkbox"
                    className="list-check"
                    aria-label={`Select ${plugin.qualified_name}`}
                    checked={checked}
                    onChange={() => onCheck(plugin)}
                />
            </td>
            <td>
                <div className="list-name">
                    <span className="list-name-icon" aria-hidden="true">
                        <Package size={17} />
                    </span>
                    <div className="list-name-content">
                        <strong title={plugin.name}>{plugin.name}</strong>
                        <span title={plugin.qualified_name}>
                            {plugin.qualified_name}
                        </span>
                    </div>
                </div>
            </td>

            <td>
                <span className="list-cell-text" title={plugin.namespace}>
                    {plugin.namespace}
                </span>
            </td>

            <td>
                <span className="list-version">{plugin.version}</span>
            </td>

            <td>
                <StatusBadge enabled={plugin.enabled} draft={plugin.draft} />
            </td>

            <td>
                <span className="list-cell-text">
                    {formatDate(plugin.installed_at)}
                </span>
            </td>

            <td className="list-operations-cell">
                <div className="list-operations">
                    {plugin.draft ? (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon entropy-button-sm"
                            aria-label={`Install ${plugin.qualified_name}`}
                            title={reasons.install ?? 'Install'}
                            aria-disabled={reasons.install ? true : undefined}
                            onClick={() => {
                                if (!reasons.install) onInstall(plugin)
                            }}
                            disabled={deleting}
                        >
                            <PackageCheck size={15} />
                        </button>
                    ) : (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon entropy-button-sm"
                            aria-label={`Test run ${plugin.qualified_name}`}
                            title={reasons.run ?? 'Test run'}
                            aria-disabled={reasons.run ? true : undefined}
                            onClick={() => {
                                if (!reasons.run) onRun(plugin)
                            }}
                            disabled={deleting || !plugin.enabled}
                        >
                            <Play size={15} />
                        </button>
                    )}
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                        aria-label={`${viewOnly ? 'View' : 'Edit'} ${plugin.qualified_name}`}
                        title={viewOnly ? 'View (read only)' : reasons.edit ?? 'Edit'}
                        aria-disabled={reasons.edit && !viewOnly ? true : undefined}
                        onClick={() => {
                            if (!reasons.edit || viewOnly) onEdit(plugin)
                        }}
                        disabled={deleting}
                    >
                        {viewOnly ? <Eye size={15} /> : <Pencil size={15} />}
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                        aria-label={`Delete ${plugin.qualified_name}`}
                        title={reasons.delete ?? 'Delete'}
                        aria-disabled={reasons.delete ? true : undefined}
                        onClick={() => {
                            if (!reasons.delete) onDelete(plugin)
                        }}
                        disabled={deleting}
                    >
                        {deleting ? (
                            <LoaderCircle size={15} className="entropy-spin" />
                        ) : (
                            <Trash2 size={15} />
                        )}
                    </button>
                    <button
                        ref={triggerRef}
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm plugins-operation-trigger"
                        aria-label={`Operations for ${plugin.name}`}
                        aria-haspopup="menu"
                        aria-expanded={menuOpen}
                        onClick={() => setMenuOpen((open) => !open)}
                    >
                        <MoreHorizontal size={18} />
                        <ChevronDown size={13} />
                    </button>

                    <FloatingMenu
                        anchorRef={triggerRef}
                        open={menuOpen}
                        onClose={closeMenu}
                        className="plugins-operation-menu"
                    >
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
                    </FloatingMenu>
                </div>
            </td>
        </tr>
    )
}

export default function Plugins() {
    const permissions = usePermissions()
    const addReason = missingPermission(permissions, ['plugins.write'], 'creating or importing plugins')
    const editReason = missingPermission(permissions, ['plugins.write'], 'editing plugins')
    const deleteReason = missingPermission(permissions, ['plugins.delete'], 'deleting plugins')
    const runReason = missingPermission(permissions, ['plugins.execute'], 'running plugins')
    const restoreReason = missingPermission(permissions, ['plugins.write'], 'restoring earlier versions')
    const viewOnly = Boolean(editReason) && !missingPermission(permissions, ['plugins.read'], 'viewing plugins')
    const rowReasons = { run: runReason, install: editReason, edit: editReason, delete: deleteReason }
    // Bumped to reopen the editor with fresh files after a restore.
    const [editorKey, setEditorKey] = useState(0)
    const [plugins, setPlugins] = useState<PluginItem[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const [searchInput, setSearchInput] = useState('')
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] =
        useState<PluginStatusFilter>('all')
    const [namespaceFilter, setNamespaceFilter] = useState('')
    const [namespaces, setNamespaces] = useState<string[]>([])
    const [sortBy, setSortBy] = useState<PluginSortField>('name')
    const [order, setOrder] = useState<SortOrder>('asc')
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [totalPages, setTotalPages] = useState(0)

    const [selectedPlugin, setSelectedPlugin] =
        useState<PluginItem | null>(null)
    const [notice, setNotice] = useState<string | null>(null)
    const [summaryTotal, setSummaryTotal] = useState(0)
    const [createOpen, setCreateOpen] = useState(() => consumeCreateIntent('plugin'))
    const [editingPlugin, setEditingPlugin] = useState<PluginItem | null>(null)
    const [deletingName, setDeletingName] = useState<string | null>(null)
    // Row picked with a click; Ctrl+D deletes it.
    const [selectedName, setSelectedName] = useState<string | null>(null)
    const [deletePickerOpen, setDeletePickerOpen] = useState(false)
    const [running, setRunning] = useState<string | null>(null)
    // The plugin whose help page is open.
    const [helpFor, setHelpFor] = useState<PluginItem | null>(null)
    // Checkbox selection (across pages) for bulk delete, export and install.
    const [checked, setChecked] = useState<Map<string, PluginItem>>(new Map())
    const [bulkBusy, setBulkBusy] = useState(false)
    const searchRef = useRef<HTMLInputElement>(null)
    const importRef = useRef<HTMLInputElement>(null)

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
                namespace: namespaceFilter || undefined,
                enabled:
                    statusFilter === 'all' || statusFilter === 'draft'
                        ? undefined
                        : statusFilter === 'enabled',
                draft: statusFilter === 'draft' ? true : undefined,
                sort_by: sortBy,
                order,
                page,
                page_size: PAGE_SIZE,
            })

            setPlugins(result.items)
            setSummaryTotal(result.summary?.total ?? result.pagination.total)
            setNamespaces(result.summary?.namespaces ?? [])
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
    }, [search, statusFilter, namespaceFilter, sortBy, order, page])

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
        setNamespaceFilter('')
        setSortBy('name')
        setOrder('asc')
        setPage(1)
    }

    const toggleChecked = (plugin: PluginItem) =>
        setChecked((current) => {
            const next = new Map(current)
            if (next.has(plugin.qualified_name)) next.delete(plugin.qualified_name)
            else next.set(plugin.qualified_name, plugin)
            return next
        })

    const pageChecked = plugins.filter((item) => checked.has(item.qualified_name)).length

    const installPlugin = async (plugin: PluginItem) => {
        try {
            const installed = await pluginsApi.install(plugin.qualified_name)
            notify.success(`${installed.qualified_name} ${installed.version} is installed and ready for workflows.`, {
                title: 'Plugin installed',
            })
            refreshPlugins()
            return true
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'Unable to install the plugin.', {
                title: `${plugin.qualified_name} not installed`,
            })
            return false
        }
    }

    const bulk = async (action: 'delete' | 'export' | 'install') => {
        const items = [...checked.values()]
        if (!items.length) return

        if (action === 'export') {
            setBulkBusy(true)
            try {
                await pluginsApi.exportZip(items.map((item) => item.qualified_name))
            } catch (cause) {
                notify.error(cause instanceof Error ? cause.message : 'Unable to export plugins.', {
                    title: 'Export failed',
                })
            } finally {
                setBulkBusy(false)
            }
            return
        }

        const targets = action === 'install' ? items.filter((item) => item.draft) : items
        if (action === 'delete') {
            const confirmed = await modal.confirm({
                title: `Delete ${targets.length} plugin${targets.length === 1 ? '' : 's'}?`,
                message:
                    `${targets.map((item) => item.qualified_name).join(', ')} will be removed. ` +
                    'Installed plugins are uninstalled; workflows that reference them will fail.',
                confirmText: targets.length === 1 ? 'Delete plugin' : `Delete ${targets.length} plugins`,
                cancelText: 'Cancel',
                destructive: true,
            })
            if (!confirmed) return
        }

        setBulkBusy(true)
        const failed: string[] = []
        for (const item of targets) {
            try {
                if (action === 'delete') await pluginsApi.delete(item.qualified_name)
                else await pluginsApi.install(item.qualified_name)
            } catch (cause) {
                failed.push(`${item.qualified_name}: ${cause instanceof Error ? cause.message : 'failed'}`)
            }
        }
        setBulkBusy(false)
        setChecked(new Map())
        refreshPlugins()

        const done = targets.length - failed.length
        if (done) {
            notify.success(
                `${done} plugin${done === 1 ? '' : 's'} ${action === 'delete' ? 'deleted' : 'installed'}.`,
            )
        }
        if (failed.length) notify.error(failed.join('\n'), { title: 'Some plugins were not changed' })
    }

    const importArchive = async (file: File | undefined) => {
        if (importRef.current) importRef.current.value = ''
        if (!file) return

        const install = await modal.confirm({
            title: `Install plugins from ${file.name}?`,
            message:
                'Imported plugins are saved as drafts. Install them now so workflows can use them, ' +
                'or keep them as drafts to review first.',
            confirmText: 'Import and install',
            cancelText: 'Import as drafts',
        })

        try {
            const result = await pluginsApi.importZip(file, install)
            notify.success(
                `${result.items.map((item) => item.qualified_name).join(', ')} ${
                    install ? 'installed' : 'saved as drafts'
                }.`,
                { title: 'Plugins imported' },
            )
            refreshPlugins()
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'Unable to import plugins.', {
                title: 'Import failed',
            })
        }
    }

    const overlayOpen =
        createOpen ||
        editingPlugin !== null ||
        selectedPlugin !== null ||
        deletePickerOpen ||
        running !== null

    const openCreate = () => {
        if (addReason) {
            notify.error(addReason, { title: 'Cannot create plugin' })
            return
        }
        setCreateOpen(true)
    }

    useCreateIntent('plugin', openCreate)

    useShortcuts(
        {
            'mod+n': openCreate,
            'alt+n': openCreate,
            'mod+f': () => {
                searchRef.current?.focus()
                searchRef.current?.select()
            },
            'mod+d': () => {
                if (deleteReason) {
                    notify.error(deleteReason, { title: 'Cannot delete plugin' })
                    return
                }
                const selected = plugins.find((item) => item.qualified_name === selectedName)

                if (selected) void handleDelete(selected)
                else setDeletePickerOpen(true)
            },
        },
        !overlayOpen,
    )

    const hasFilters =
        searchInput.trim() !== '' || statusFilter !== 'all' || namespaceFilter !== ''

    return (
        <section className="list-page">
            {error && (
                <div className="list-error" role="alert">
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        onClick={refreshPlugins}
                        disabled={refreshing}
                    >
                        Retry
                    </button>
                </div>
            )}

            {notice && (
                <div className="list-notice" role="status">
                    <Check size={16} />
                    <span>{notice}</span>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label="Dismiss notification"
                        onClick={() => setNotice(null)}
                    >
                        <X size={15} />
                    </button>
                </div>
            )}

            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Installed plugins
                            <span
                                className="list-count"
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

                    <div className="entropy-panel-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh plugins"
                            title="Refresh"
                            onClick={refreshPlugins}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
<AddMenu
                            label="Add plugin"
                            onCreate={openCreate}
                            onImport={() => importRef.current?.click()}
                            importLabel="Import from zip…"
                            disabledReason={addReason}
                        />
                        <input
                            ref={importRef}
                            type="file"
                            accept=".zip,application/zip"
                            hidden
                            onChange={(event) => void importArchive(event.target.files?.[0])}
                        />
                    </div>
                </div>

                <div className="list-toolbar">
                    <div className="list-search">
                        <Search size={17} aria-hidden="true" />
                        <input
                            ref={searchRef}
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

                    <div className="list-toolbar-actions">
                        <label className="list-filter">
                            <span>Namespace</span>
                            <select
                                className="entropy-select"
                                value={namespaceFilter}
                                onChange={(event) => {
                                    setNamespaceFilter(event.target.value)
                                    setPage(1)
                                }}
                                aria-label="Filter plugins by namespace"
                            >
                                <option value="">All namespaces</option>
                                {/* Keep a filtered namespace selectable even if it disappears. */}
                                {namespaceFilter && !namespaces.includes(namespaceFilter) && (
                                    <option value={namespaceFilter}>{namespaceFilter}</option>
                                )}
                                {namespaces.map((namespace) => (
                                    <option key={namespace} value={namespace}>
                                        {namespace}
                                    </option>
                                ))}
                            </select>
                        </label>

                        <label className="list-filter">
                            <span>Status</span>
                            <select
                                className="entropy-select"
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
                                <option value="draft">Drafts</option>
                            </select>
                        </label>

                        {hasFilters && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={clearFilters}
                            >
                                Clear filters
                            </button>
                        )}
                    </div>
                    {checked.size > 0 && (
                        <div className="list-bulk" role="toolbar" aria-label="Selected plugins">
                            <span>{checked.size} selected</span>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => void bulk('export')}
                                disabled={bulkBusy}
                            >
                                <Download size={14} /> Export
                            </button>
                            {[...checked.values()].some((item) => item.draft) && (
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-secondary entropy-button-sm"
                                    onClick={() => {
                                        if (!editReason) void bulk('install')
                                    }}
                                    disabled={bulkBusy}
                                    aria-disabled={editReason ? true : undefined}
                                    title={editReason ?? undefined}
                                >
                                    <PackageCheck size={14} /> Install drafts
                                </button>
                            )}
                            <button
                                type="button"
                                className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                                onClick={() => {
                                    if (!deleteReason) void bulk('delete')
                                }}
                                disabled={bulkBusy}
                                aria-disabled={deleteReason ? true : undefined}
                                title={deleteReason ?? undefined}
                            >
                                {bulkBusy ? <LoaderCircle size={14} className="entropy-spin" /> : <Trash2 size={14} />}
                                Delete
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={() => setChecked(new Map())}
                            >
                                Clear
                            </button>
                        </div>
                    )}
                </div>

                <div className="list-table-wrap">
                    <table className="list-table">
                        <thead>
                            <tr>
                                <th scope="col" className="list-check-cell">
                                    <input
                                        type="checkbox"
                                        className="list-check"
                                        aria-label="Select all plugins on this page"
                                        checked={plugins.length > 0 && pageChecked === plugins.length}
                                        ref={(element) => {
                                            if (element) {
                                                element.indeterminate = pageChecked > 0 && pageChecked < plugins.length
                                            }
                                        }}
                                        onChange={(event) =>
                                            setChecked((current) => {
                                                const next = new Map(current)
                                                plugins.forEach((item) => {
                                                    if (event.target.checked) next.set(item.qualified_name, item)
                                                    else next.delete(item.qualified_name)
                                                })
                                                return next
                                            })
                                        }
                                        disabled={plugins.length === 0}
                                    />
                                </th>
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
                                    <span className="list-operations-heading">
                                        Operations
                                    </span>
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {loading && plugins.length === 0 ? (
                                <tr>
                                    <td colSpan={7}>
                                        <div
                                            className="list-loading"
                                            role="status"
                                        >
                                            <RefreshCw
                                                size={19}
                                                className="entropy-spin"
                                            />
                                            <span>Loading plugins…</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : plugins.length > 0 ? (
                                plugins.map((plugin) => (
                                    <PluginRow
                                        key={plugin.qualified_name}
                                        plugin={plugin}
                                        checked={checked.has(plugin.qualified_name)}
                                        onCheck={toggleChecked}
                                        onRun={(item) => setRunning(item.qualified_name)}
                                        onInstall={(item) => void installPlugin(item)}
                                        deleting={deletingName === plugin.qualified_name}
                                        selected={selectedName === plugin.qualified_name}
                                        onSelect={(item) => {
                                            setSelectedName(item.qualified_name)
                                            setHelpFor(item)
                                        }}
                                        onCopy={(value) => void handleCopy(value)}
                                        onViewDetails={setHelpFor}
                                        onEdit={setEditingPlugin}
                                        onDelete={(item) => void handleDelete(item)}
                                        reasons={rowReasons}
                                        viewOnly={viewOnly}
                                    />
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={7}>
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

                <footer className="list-pagination">
                    <span>
                        {total === 0
                            ? 'No plugins'
                            : `Showing ${(page - 1) * PAGE_SIZE + 1}–${Math.min(
                                  page * PAGE_SIZE,
                                  total,
                              )} of ${total}`}
                    </span>

                    <div className="list-pagination-controls">
                        <label htmlFor="list-page-select">Page</label>
                        <select
                            id="list-page-select"
                            className="entropy-select list-page-select"
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
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label="Previous page"
                            disabled={page <= 1 || loading}
                            onClick={() => setPage((current) => current - 1)}
                        >
                            <ChevronLeft size={17} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
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
                                    <p className="page-eyebrow">
                                        PLUGIN DETAILS
                                    </p>
                                    <h2 id="plugins-details-title">
                                        {selectedPlugin.name}
                                    </h2>
                                </div>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
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
                                            draft={selectedPlugin.draft}
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
                                    <dd>{selectedPlugin.id ?? 'Not installed'}</dd>
                                </div>
                            </dl>

                            <footer className="plugins-modal-footer">
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-secondary"
                                    onClick={() => setSelectedPlugin(null)}
                                >
                                    Close
                                </button>
                            </footer>
                        </section>
                    </div>
                </AppPortal>
            )}

            {deletePickerOpen && (
                <PickerDialog
                    title="Delete which plugin?"
                    subtitle="No plugin is selected. Choose the plugin to delete."
                    icon={<Trash2 size={18} />}
                    placeholder="Search plugins"
                    empty="No plugins match your search."
                    load={async (query) =>
                        (await listPlugins({ q: query || undefined, page_size: PAGE_SIZE })).items.map(
                            (item) => ({
                                id: item.qualified_name,
                                label: item.qualified_name,
                                detail: `${item.version} · ${item.enabled ? 'Enabled' : 'Disabled'}`,
                            }),
                        )
                    }
                    onPick={async (item) => {
                        const result = await listPlugins({ q: item.id, page_size: PAGE_SIZE })
                        const plugin = result.items.find((entry) => entry.qualified_name === item.id)
                        if (plugin) void handleDelete(plugin)
                    }}
                    onClose={() => setDeletePickerOpen(false)}
                />
            )}

            {running && <StartRunDialog kind="plugin" target={running} onClose={() => setRunning(null)} />}

            {helpFor && !editingPlugin && (
                <AppPortal>
                    <Suspense
                        fallback={
                            <div className="plugins-modal-backdrop" role="status">
                                <LoaderCircle size={24} className="entropy-spin" />
                            </div>
                        }
                    >
                        <PluginHelp
                            qualifiedName={helpFor.qualified_name}
                            onClose={() => setHelpFor(null)}
                            onRun={helpFor.draft ? undefined : () => setRunning(helpFor.qualified_name)}
                            runReason={runReason}
                            onEdit={editReason && !viewOnly ? undefined : () => setEditingPlugin(helpFor)}
                            editLabel={viewOnly ? 'View source' : 'Edit'}
                        />
                    </Suspense>
                </AppPortal>
            )}

            {createOpen && (
                <AppPortal>
                    <CreatePluginModal
                        onClose={() => setCreateOpen(false)}
                        onCreated={(plugin) => {
                            setCreateOpen(false)
                            notify.success(
                                `${plugin.qualified_name} was saved as a draft. Install it to use it in workflows.`,
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
                                <LoaderCircle size={24} className="entropy-spin" />
                            </div>
                        }
                    >
                        <PluginEditor
                            key={`${editingPlugin.qualified_name}:${editorKey}`}
                            plugin={editingPlugin}
                            onClose={() => setEditingPlugin(null)}
                            onSaved={() => {
                                setEditingPlugin(null)
                                refreshPlugins()
                            }}
                            readOnly={viewOnly}
                            restoreReason={restoreReason}
                            onRestored={(version) => {
                                setEditingPlugin((current) => (current ? { ...current, version } : current))
                                setEditorKey((value) => value + 1)
                                refreshPlugins()
                            }}
                        />
                    </Suspense>
                </AppPortal>
            )}
        </section>
    )
}
