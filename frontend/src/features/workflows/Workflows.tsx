import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    LoaderCircle,
    Pencil,
    Plus,
    RefreshCw,
    Search,
    Trash2,
    Workflow as WorkflowIcon,
    X,
} from 'lucide-react'

import { workflowsApi, type WorkflowSummary } from '../../api/workflows.api'
import AppPortal from '../../components/layout/AppPortal'
import { useFeedback } from '../../components/feedback/FeedbackProvider'

// The builder pulls in Monaco and YAML; load it only when opened.
const WorkflowBuilder = lazy(() => import('./builder/WorkflowBuilder'))

type BuilderTarget = { mode: 'create' } | { mode: 'edit'; name: string } | null

function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

function formatDate(value: string): string {
    const date = new Date(value)

    return Number.isNaN(date.getTime())
        ? '—'
        : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export default function Workflows() {
    const { notify, modal } = useFeedback()

    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [search, setSearch] = useState('')
    const [builder, setBuilder] = useState<BuilderTarget>(null)
    const [deleting, setDeleting] = useState<string | null>(null)

    const loadWorkflows = useCallback(async () => {
        try {
            const response = await workflowsApi.list()
            setWorkflows(response.items)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load workflows.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        let active = true

        workflowsApi
            .list()
            .then((response) => {
                if (active) setWorkflows(response.items)
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load workflows.'))
            })
            .finally(() => {
                if (active) setLoading(false)
            })

        return () => {
            active = false
        }
    }, [])

    const refresh = () => {
        setRefreshing(true)
        void loadWorkflows()
    }

    const remove = async (workflow: WorkflowSummary) => {
        const confirmed = await modal.confirm({
            title: `Delete ${workflow.name}?`,
            message: 'The workflow is removed from the registry. This cannot be undone.',
            confirmText: 'Delete workflow',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setDeleting(workflow.name)

        try {
            await workflowsApi.delete(workflow.name)
            notify.success(`Workflow '${workflow.name}' deleted.`, { title: 'Workflow deleted' })
            refresh()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the workflow.'), { title: 'Delete failed' })
        } finally {
            setDeleting(null)
        }
    }

    const filtered = useMemo(() => {
        const query = search.trim().toLowerCase()

        return query
            ? workflows.filter((workflow) =>
                  `${workflow.name} ${workflow.description}`.toLowerCase().includes(query),
              )
            : workflows
    }, [search, workflows])

    return (
        <section className="workflows-page">
            <header className="page-heading">
                <div>
                    <p className="page-eyebrow">DEPLOYMENT WORKSPACE</p>
                    <h1>Workflows</h1>
                    <p className="page-subtitle">Create, validate, and manage deployment workflows.</p>
                </div>

                <div className="page-heading-actions">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={refresh}
                        disabled={loading || refreshing}
                    >
                        <RefreshCw size={15} className={refreshing ? 'entropy-spin' : ''} />
                        Refresh
                    </button>
                </div>
            </header>

            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            <section className="workflows-section">
                <div className="workflows-section-heading">
                    <div>
                        <h2>
                            Available workflows
                            <span className="entropy-count" aria-label={`${workflows.length} workflows in total`}>
                                {workflows.length}
                            </span>
                        </h2>
                        <p>
                            {filtered.length} workflow{filtered.length === 1 ? '' : 's'}{' '}
                            {search.trim() ? 'match your search' : 'registered'}
                        </p>
                    </div>

                    <button
                        type="button"
                        className="entropy-button entropy-button-primary entropy-button-icon"
                        aria-label="Create workflow"
                        title="Create workflow"
                        onClick={() => setBuilder({ mode: 'create' })}
                    >
                        <Plus size={20} />
                    </button>
                </div>

                <label className="entropy-search workflows-search">
                    <Search size={15} aria-hidden="true" />
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search workflows…"
                        aria-label="Search workflows"
                    />
                    {search && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                            aria-label="Clear search"
                            onClick={() => setSearch('')}
                        >
                            <X size={14} />
                        </button>
                    )}
                </label>

                <div className="workflows-table-wrap">
                    <table className="workflows-table">
                        <thead>
                            <tr>
                                <th scope="col">Workflow</th>
                                <th scope="col">Version</th>
                                <th scope="col">Updated</th>
                                <th scope="col" className="workflows-operations-heading">
                                    Operations
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={4}>
                                        <div className="workflows-empty" role="status">
                                            <LoaderCircle size={18} className="entropy-spin" />
                                            Loading workflows…
                                        </div>
                                    </td>
                                </tr>
                            ) : filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={4}>
                                        <div className="workflows-empty">
                                            <WorkflowIcon size={22} />
                                            <strong>
                                                {workflows.length === 0 ? 'No workflows yet' : 'No workflows found'}
                                            </strong>
                                            <span>
                                                {workflows.length === 0
                                                    ? 'Create one with the + button.'
                                                    : 'Try a different search.'}
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((workflow) => (
                                    <tr key={workflow.name}>
                                        <td>
                                            <div className="workflows-name">
                                                <span className="workflows-name-icon" aria-hidden="true">
                                                    <WorkflowIcon size={16} />
                                                </span>
                                                <div>
                                                    <strong>{workflow.name}</strong>
                                                    <span>{workflow.description || 'No description'}</span>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <span className="plugins-version">{workflow.version}</span>
                                        </td>
                                        <td className="workflows-muted">{formatDate(workflow.updated_at)}</td>
                                        <td>
                                            <div className="workflows-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Edit ${workflow.name}`}
                                                    title="Edit"
                                                    onClick={() => setBuilder({ mode: 'edit', name: workflow.name })}
                                                    disabled={deleting === workflow.name}
                                                >
                                                    <Pencil size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                    aria-label={`Delete ${workflow.name}`}
                                                    title="Delete"
                                                    onClick={() => void remove(workflow)}
                                                    disabled={deleting === workflow.name}
                                                >
                                                    {deleting === workflow.name ? (
                                                        <LoaderCircle size={15} className="entropy-spin" />
                                                    ) : (
                                                        <Trash2 size={15} />
                                                    )}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            {builder && (
                <AppPortal>
                    <Suspense
                        fallback={
                            <div className="plugins-modal-backdrop" role="status">
                                <LoaderCircle size={24} className="entropy-spin" />
                            </div>
                        }
                    >
                        <WorkflowBuilder
                            key={builder.mode === 'edit' ? builder.name : 'new'}
                            name={builder.mode === 'edit' ? builder.name : undefined}
                            onClose={() => setBuilder(null)}
                            onSaved={() => {
                                setBuilder(null)
                                refresh()
                            }}
                        />
                    </Suspense>
                </AppPortal>
            )}
        </section>
    )
}
