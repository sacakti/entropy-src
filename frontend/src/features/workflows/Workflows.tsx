import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    CheckCircle2,
    FilePlus2,
    LoaderCircle,
    RefreshCw,
    Save,
    Search,
    Trash2,
    Workflow,
} from 'lucide-react'

import {
    workflowsApi,
    type WorkflowDetail,
    type WorkflowFormat,
    type WorkflowSummary,
} from '../../api/workflows.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'

const NEW_WORKFLOW = `{
    "name": "new_workflow",
    "version": "1.0.0",
    "description": "",
    "variables": {},
    "steps": []
}
`

type Selection =
    | { kind: 'none' }
    | { kind: 'new' }
    | { kind: 'existing'; name: string }

function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

function formatDate(value: string): string {
    const date = new Date(value)

    return Number.isNaN(date.getTime())
        ? '—'
        : new Intl.DateTimeFormat(undefined, {
              dateStyle: 'medium',
              timeStyle: 'short',
          }).format(date)
}

export default function Workflows() {
    const { notify, modal } = useFeedback()

    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
    const [loadingList, setLoadingList] = useState(true)
    const [listError, setListError] = useState<string | null>(null)
    const [search, setSearch] = useState('')

    const [selection, setSelection] = useState<Selection>({ kind: 'none' })
    const [detail, setDetail] = useState<WorkflowDetail | null>(null)
    const [format, setFormat] = useState<WorkflowFormat>('json')
    const [definition, setDefinition] = useState('')
    const [savedDefinition, setSavedDefinition] = useState('')
    const [loadingDetail, setLoadingDetail] = useState(false)
    const [busy, setBusy] = useState<'validate' | 'save' | 'delete' | null>(null)
    const [result, setResult] = useState<
        { kind: 'success' | 'error'; message: string } | null
    >(null)

    const dirty = definition !== savedDefinition

    const loadWorkflows = useCallback(async () => {
        try {
            const response = await workflowsApi.list()
            setWorkflows(response.items)
            setListError(null)
        } catch (error) {
            setListError(errorMessage(error, 'Unable to load workflows.'))
        } finally {
            setLoadingList(false)
        }
    }, [])

    useEffect(() => {
        let active = true

        workflowsApi
            .list()
            .then((response) => {
                if (active) setWorkflows(response.items)
            })
            .catch((error: unknown) => {
                if (active) setListError(errorMessage(error, 'Unable to load workflows.'))
            })
            .finally(() => {
                if (active) setLoadingList(false)
            })

        return () => {
            active = false
        }
    }, [])

    const openWorkflow = useCallback(
        async (name: string, nextFormat: WorkflowFormat) => {
            setLoadingDetail(true)
            setResult(null)

            try {
                const response = await workflowsApi.get(name, nextFormat)
                setSelection({ kind: 'existing', name })
                setDetail(response)
                setFormat(nextFormat)
                setDefinition(response.definition)
                setSavedDefinition(response.definition)
            } catch (error) {
                notify.error(errorMessage(error, 'Unable to open workflow.'), {
                    title: 'Workflow unavailable',
                })
            } finally {
                setLoadingDetail(false)
            }
        },
        [notify],
    )

    const confirmDiscard = async (): Promise<boolean> =>
        !dirty ||
        modal.confirm({
            title: 'Discard unsaved changes?',
            message: 'Your edits to this workflow definition will be lost.',
            confirmText: 'Discard',
            cancelText: 'Keep editing',
            destructive: true,
        })

    const select = async (name: string) => {
        if (selection.kind === 'existing' && selection.name === name) return
        if (!(await confirmDiscard())) return

        await openWorkflow(name, format)
    }

    const startNew = async () => {
        if (!(await confirmDiscard())) return

        setSelection({ kind: 'new' })
        setDetail(null)
        setFormat('json')
        setDefinition(NEW_WORKFLOW)
        setSavedDefinition('')
        setResult(null)
    }

    const changeFormat = async (nextFormat: WorkflowFormat) => {
        if (selection.kind !== 'existing') {
            setFormat(nextFormat)
            return
        }

        if (!(await confirmDiscard())) return

        await openWorkflow(selection.name, nextFormat)
    }

    const validate = async () => {
        setBusy('validate')

        try {
            const response = await workflowsApi.validate({ definition, format })
            setResult({
                kind: 'success',
                message: `Valid workflow '${response.workflow.name}' with ${response.workflow.step_count} step${
                    response.workflow.step_count === 1 ? '' : 's'
                }.`,
            })
        } catch (error) {
            setResult({ kind: 'error', message: errorMessage(error, 'Validation failed.') })
        } finally {
            setBusy(null)
        }
    }

    const save = async () => {
        setBusy('save')

        try {
            const saved =
                selection.kind === 'existing'
                    ? await workflowsApi.update(selection.name, { definition, format })
                    : await workflowsApi.create({ definition, format })

            setSelection({ kind: 'existing', name: saved.name })
            setDetail(saved)
            setDefinition(saved.definition)
            setSavedDefinition(saved.definition)
            setResult(null)
            notify.success(`Workflow '${saved.name}' saved.`, { title: 'Workflow saved' })
            void loadWorkflows()
        } catch (error) {
            setResult({ kind: 'error', message: errorMessage(error, 'Unable to save workflow.') })
        } finally {
            setBusy(null)
        }
    }

    const remove = async () => {
        if (selection.kind !== 'existing') return

        const confirmed = await modal.confirm({
            title: `Delete ${selection.name}?`,
            message: 'The workflow is removed from the registry. This cannot be undone.',
            confirmText: 'Delete workflow',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setBusy('delete')

        try {
            await workflowsApi.delete(selection.name)
            notify.success(`Workflow '${selection.name}' deleted.`, {
                title: 'Workflow deleted',
            })
            setSelection({ kind: 'none' })
            setDetail(null)
            setDefinition('')
            setSavedDefinition('')
            void loadWorkflows()
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to delete workflow.'), {
                title: 'Delete failed',
            })
        } finally {
            setBusy(null)
        }
    }

    // The detail endpoint has no timestamps; take them from the list entry.
    const updatedAt =
        detail && workflows.find((workflow) => workflow.name === detail.name)?.updated_at

    const filtered = useMemo(() => {
        const query = search.trim().toLowerCase()

        return query
            ? workflows.filter(
                  (workflow) =>
                      workflow.name.toLowerCase().includes(query) ||
                      workflow.description.toLowerCase().includes(query),
              )
            : workflows
    }, [search, workflows])

    return (
        <section className="workflows-page">
            <header className="page-heading">
                <div>
                    <p className="page-eyebrow">DEPLOYMENT WORKSPACE</p>
                    <h1>Workflows</h1>
                    <p className="page-subtitle">
                        Create, validate, and manage deployment workflows.
                    </p>
                </div>

                <div className="page-heading-actions">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => {
                            setLoadingList(true)
                            void loadWorkflows()
                        }}
                        disabled={loadingList}
                    >
                        <RefreshCw size={15} className={loadingList ? 'entropy-spin' : ''} />
                        Refresh
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => void startNew()}
                    >
                        <FilePlus2 size={15} />
                        New workflow
                    </button>
                </div>
            </header>

            <div className="workflows-layout">
                <aside className="workflow-list-panel" aria-label="Workflows">
                    <div className="workflow-list-heading">
                        <h2>Registered</h2>
                        <span className="entropy-count">{workflows.length}</span>
                    </div>

                    <label className="entropy-search workflow-search">
                        <Search size={15} aria-hidden="true" />
                        <input
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search workflows…"
                            aria-label="Search workflows"
                        />
                    </label>

                    {loadingList && workflows.length === 0 ? (
                        <p className="workflow-empty">
                            <LoaderCircle size={14} className="entropy-spin" /> Loading workflows…
                        </p>
                    ) : listError ? (
                        <div className="entropy-alert entropy-alert-error" role="alert">
                            {listError}
                        </div>
                    ) : filtered.length === 0 ? (
                        <p className="workflow-empty">
                            {workflows.length === 0
                                ? 'No workflows are registered yet. Create one to get started.'
                                : 'No workflows match your search.'}
                        </p>
                    ) : (
                        <div className="workflow-list">
                            {filtered.map((workflow) => (
                                <button
                                    key={workflow.name}
                                    type="button"
                                    className={`workflow-list-item${
                                        selection.kind === 'existing' &&
                                        selection.name === workflow.name
                                            ? ' is-selected'
                                            : ''
                                    }`}
                                    onClick={() => void select(workflow.name)}
                                >
                                    <strong>{workflow.name}</strong>
                                    <span>
                                        v{workflow.version} · updated {formatDate(workflow.updated_at)}
                                    </span>
                                    {workflow.description && <small>{workflow.description}</small>}
                                </button>
                            ))}
                        </div>
                    )}
                </aside>

                <section className="workflow-editor-panel" aria-label="Workflow definition">
                    {selection.kind === 'none' ? (
                        <div className="workflow-editor-empty">
                            <span className="placeholder-icon">
                                <Workflow size={22} />
                            </span>
                            <h3>Select a workflow</h3>
                            <p>Choose a workflow to view or edit it, or create a new one.</p>
                        </div>
                    ) : (
                        <>
                            <div className="workflow-editor-heading">
                                <div>
                                    <h2>
                                        {selection.kind === 'new'
                                            ? 'New workflow'
                                            : selection.name}
                                    </h2>
                                    <p>
                                        {detail?.description ||
                                            (selection.kind === 'new'
                                                ? 'Write a definition, validate it, then create it.'
                                                : 'No description.')}
                                    </p>
                                </div>

                                <label className="workflow-format-control">
                                    <span>Format</span>
                                    <select
                                        className="entropy-select"
                                        value={format}
                                        onChange={(event) =>
                                            void changeFormat(event.target.value as WorkflowFormat)
                                        }
                                        disabled={loadingDetail || busy !== null}
                                    >
                                        <option value="json">JSON</option>
                                        <option value="yaml">YAML</option>
                                    </select>
                                </label>
                            </div>

                            {detail && (
                                <dl className="workflow-metadata">
                                    <div>
                                        <dt>Version</dt>
                                        <dd>{detail.version}</dd>
                                    </div>
                                    <div>
                                        <dt>Steps</dt>
                                        <dd>{detail.step_count}</dd>
                                    </div>
                                    <div>
                                        <dt>Updated</dt>
                                        <dd>{updatedAt ? formatDate(updatedAt) : '—'}</dd>
                                    </div>
                                </dl>
                            )}

                            <label className="workflow-definition-label" htmlFor="workflow-definition">
                                Definition
                            </label>
                            <textarea
                                id="workflow-definition"
                                className="workflow-definition-editor"
                                value={definition}
                                onChange={(event) => setDefinition(event.target.value)}
                                spellCheck={false}
                                disabled={loadingDetail}
                            />

                            {result && (
                                <div
                                    className={`entropy-alert entropy-alert-${result.kind}`}
                                    role={result.kind === 'error' ? 'alert' : 'status'}
                                >
                                    {result.kind === 'success' && <CheckCircle2 size={15} />}
                                    <span>{result.message}</span>
                                </div>
                            )}

                            <footer className="workflow-editor-footer">
                                <span>{dirty ? 'Unsaved changes' : 'No unsaved changes'}</span>

                                <div className="workflow-editor-actions">
                                    {selection.kind === 'existing' && (
                                        <button
                                            type="button"
                                            className="entropy-button entropy-button-danger"
                                            onClick={() => void remove()}
                                            disabled={busy !== null}
                                        >
                                            <Trash2 size={15} />
                                            Delete
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary"
                                        onClick={() => void validate()}
                                        disabled={busy !== null || !definition.trim()}
                                    >
                                        {busy === 'validate' ? (
                                            <LoaderCircle size={15} className="entropy-spin" />
                                        ) : (
                                            <CheckCircle2 size={15} />
                                        )}
                                        Validate
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-primary"
                                        onClick={() => void save()}
                                        disabled={busy !== null || !dirty || !definition.trim()}
                                    >
                                        {busy === 'save' ? (
                                            <LoaderCircle size={15} className="entropy-spin" />
                                        ) : (
                                            <Save size={15} />
                                        )}
                                        {selection.kind === 'new' ? 'Create workflow' : 'Save changes'}
                                    </button>
                                </div>
                            </footer>
                        </>
                    )}
                </section>
            </div>
        </section>
    )
}
