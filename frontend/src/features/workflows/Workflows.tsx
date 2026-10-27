import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
    ArrowRightLeft,
    BellRing,
    Download,
    FileWarning,
    LoaderCircle,
    Pencil,
    Eye,
    Play,
    RefreshCw,
    Search,
    Trash2,
    Workflow as WorkflowIcon,
    X,
} from 'lucide-react'

import {
    workflowDraftsApi,
    workflowsApi,
    type WorkflowDraftSummary,
    type WorkflowFormat,
    type WorkflowSummary,
} from '../../api/workflows.api'
import { ApiError } from '../../services/api'
import AddMenu from '../../components/layout/AddMenu'
import { missingPermission as missing } from '../administration/permissionReason'
import { usePermissions } from '../administration/usePermissions'
import AppPortal from '../../components/layout/AppPortal'
import StartRunDialog from '../runs/StartRunDialog'
import RunAlertsDialog from '../runs/RunAlertsDialog'
import { MoveToProjectDialog } from '../transfer/TransferDialogs'
import PickerDialog from '../../components/layout/PickerDialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

// The builder pulls in Monaco and YAML; load it only when opened.
const WorkflowBuilder = lazy(() => import('./builder/WorkflowBuilder'))

type BuilderTarget =
    | { mode: 'create' }
    | { mode: 'edit'; name: string }
    // A draft saved with errors; `workflow` is the registered workflow it edits.
    | { mode: 'draft'; id: number; workflow: string | null }
    | null

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
    const permissions = usePermissions()
    const addReason = missing(permissions, ['workflows.write', 'plugins.read'], 'creating or importing workflows')
    const editReason = missing(permissions, ['workflows.write', 'plugins.read'], 'editing workflows')
    const deleteReason = missing(permissions, ['workflows.delete'], 'deleting workflows')
    const runReason = missing(permissions, ['workflows.execute'], 'running workflows')
    const restoreReason = missing(permissions, ['workflows.write', 'plugins.read'], 'restoring earlier versions')
    // Without write access the definition can still be viewed.
    const viewOnly = Boolean(editReason) && !missing(permissions, ['workflows.read'], 'viewing workflows')

    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
    const [drafts, setDrafts] = useState<WorkflowDraftSummary[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [search, setSearch] = useState('')
    const [builder, setBuilder] = useState<BuilderTarget>(() =>
        consumeCreateIntent('workflow') ? { mode: 'create' } : null,
    )
    const [deleting, setDeleting] = useState<string | null>(null)
    // Row picked with a click; Ctrl+D deletes it.
    const [selectedName, setSelectedName] = useState<string | null>(null)
    const [deletePickerOpen, setDeletePickerOpen] = useState(false)
    const [running, setRunning] = useState<string | null>(null)
    const [alerting, setAlerting] = useState<string | null>(null)
    // Checkbox selection for bulk delete and export.
    const [checked, setChecked] = useState<Set<string>>(new Set())
    const [moving, setMoving] = useState<string[] | null>(null)
    const [bulkBusy, setBulkBusy] = useState(false)
    const searchRef = useRef<HTMLInputElement>(null)
    const importRef = useRef<HTMLInputElement>(null)

    const loadDrafts = useCallback(() => {
        // Drafts are a convenience: the list works without them.
        workflowDraftsApi
            .list()
            .then((response) => setDrafts(response.items))
            .catch(() => setDrafts([]))
    }, [])

    useEffect(() => {
        loadDrafts()
    }, [loadDrafts])

    const loadWorkflows = useCallback(async () => {
        loadDrafts()
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
    }, [loadDrafts])

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

    const openCreate = () => {
        if (addReason) {
            notify.error(addReason, { title: 'Cannot create workflow' })
            return
        }
        setBuilder({ mode: 'create' })
    }

    const toggleChecked = (name: string) =>
        setChecked((current) => {
            const next = new Set(current)
            if (next.has(name)) next.delete(name)
            else next.add(name)
            return next
        })

    const removeChecked = async () => {
        const names = workflows.filter((item) => checked.has(item.name)).map((item) => item.name)
        if (!names.length) return

        const confirmed = await modal.confirm({
            title: `Delete ${names.length} workflow${names.length === 1 ? '' : 's'}?`,
            message: `${names.join(', ')} will be removed from the registry. This cannot be undone.`,
            confirmText: names.length === 1 ? 'Delete workflow' : `Delete ${names.length} workflows`,
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return

        setBulkBusy(true)
        const failed: string[] = []
        for (const name of names) {
            try {
                await workflowsApi.delete(name)
            } catch {
                failed.push(name)
            }
        }
        setBulkBusy(false)
        setChecked(new Set(failed))

        if (failed.length) {
            notify.error(`Could not delete ${failed.join(', ')}.`, { title: 'Delete incomplete' })
        } else {
            notify.success(`${names.length} workflow${names.length === 1 ? '' : 's'} deleted.`)
        }
        refresh()
    }

    const exportChecked = async (format: WorkflowFormat) => {
        setBulkBusy(true)
        try {
            await workflowsApi.exportZip([...checked], format)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to export workflows.'), { title: 'Export failed' })
        } finally {
            setBulkBusy(false)
        }
    }

    // Import JSON/YAML definitions; an existing name is replaced only after asking.
    const importFiles = async (files: FileList | null) => {
        if (!files?.length) return
        const imported: string[] = []
        const failed: string[] = []

        for (const file of Array.from(files)) {
            const extension = file.name.split('.').pop()?.toLowerCase()
            const format: WorkflowFormat = extension === 'yaml' || extension === 'yml' ? extension : 'json'
            const definition = await file.text()

            try {
                const created = await workflowsApi.create({ definition, format })
                imported.push(created.name)
            } catch (cause) {
                if (cause instanceof ApiError && cause.status === 409) {
                    const validated = await workflowsApi.validate({ definition, format }).catch(() => null)
                    const name = validated?.workflow.name
                    const replace =
                        name &&
                        (await modal.confirm({
                            title: `Replace ${name}?`,
                            message: `A workflow named '${name}' already exists. Importing ${file.name} replaces it and raises its version.`,
                            confirmText: 'Replace',
                            cancelText: 'Skip',
                        }))
                    if (replace && name) {
                        try {
                            await workflowsApi.update(name, { definition, format })
                            imported.push(name)
                        } catch (error) {
                            failed.push(`${file.name}: ${errorMessage(error, 'invalid')}`)
                        }
                    }
                } else {
                    failed.push(`${file.name}: ${errorMessage(cause, 'invalid')}`)
                }
            }
        }

        if (importRef.current) importRef.current.value = ''
        if (imported.length) {
            notify.success(`Imported ${imported.join(', ')}.`, { title: 'Workflows imported' })
            refresh()
        }
        if (failed.length) notify.error(failed.join('\n'), { title: 'Some files were not imported' })
    }

    useCreateIntent('workflow', openCreate)

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
                    notify.error(deleteReason, { title: 'Cannot delete workflow' })
                    return
                }
                const selected = workflows.find((item) => item.name === selectedName)

                if (selected) void remove(selected)
                else setDeletePickerOpen(true)
            },
        },
        builder === null && !deletePickerOpen && running === null,
    )

    const draftOf = useMemo(
        () => new Map(drafts.filter((item) => item.workflow).map((item) => [item.workflow as string, item])),
        [drafts],
    )

    // Drafts of workflows that were never saved, listed before the workflows.
    const newDrafts = useMemo(() => {
        const query = search.trim().toLowerCase()
        return drafts.filter(
            (item) => item.workflow === null && (!query || item.title.toLowerCase().includes(query)),
        )
    }, [drafts, search])

    const discardDraft = async (item: WorkflowDraftSummary) => {
        const confirmed = await modal.confirm({
            title: `Discard the draft '${item.title}'?`,
            message: 'The workflow saved with errors is deleted. This cannot be undone.',
            confirmText: 'Discard draft',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        try {
            await workflowDraftsApi.delete(item.id)
            notify.success(`Draft '${item.title}' discarded.`)
            loadDrafts()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to discard the draft.'))
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
        <section className="list-page workflows-page">

            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Available workflows
                            <span className="list-count" aria-label={`${workflows.length} workflows in total`}>
                                {workflows.length}
                            </span>
                        </h2>
                        <p>
                            {filtered.length} workflow{filtered.length === 1 ? '' : 's'}{' '}
                            {search.trim() ? 'match your search' : 'registered'}
                        </p>
                    </div>

                    <div className="entropy-panel-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh workflows"
                            title="Refresh"
                            onClick={refresh}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
<AddMenu
                            label="Add workflow"
                            onCreate={openCreate}
                            onImport={() => importRef.current?.click()}
                            importLabel="Import JSON / YAML…"
                            disabledReason={addReason}
                        />
                        <input
                            ref={importRef}
                            type="file"
                            accept=".json,.yaml,.yml,application/json,application/yaml"
                            multiple
                            hidden
                            onChange={(event) => void importFiles(event.target.files)}
                        />
                    </div>
                </div>

                <div className="list-toolbar">
                <div className="list-search">
                    <Search size={17} aria-hidden="true" />
                    <input
                        ref={searchRef}
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search workflows…"
                        aria-label="Search workflows"
                    />
                    {search && (
                        <button type="button" aria-label="Clear search" onClick={() => setSearch('')}>
                            <X size={15} />
                        </button>
                    )}
                </div>
                {checked.size > 0 && (
                    <div className="list-bulk" role="toolbar" aria-label="Selected workflows">
                        <span>{checked.size} selected</span>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            onClick={() => void exportChecked('json')}
                            disabled={bulkBusy}
                        >
                            <Download size={14} /> Export JSON
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            onClick={() => void exportChecked('yaml')}
                            disabled={bulkBusy}
                        >
                            <Download size={14} /> Export YAML
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            onClick={() => setMoving([...checked])}
                            disabled={bulkBusy || Boolean(editReason)}
                            title={editReason ?? 'Move or copy to another project'}
                        >
                            <ArrowRightLeft size={14} /> Move or copy
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                            onClick={() => {
                                if (!deleteReason) void removeChecked()
                            }}
                            disabled={bulkBusy}
                            aria-disabled={deleteReason ? true : undefined}
                            title={deleteReason ?? undefined}
                        >
                            {bulkBusy ? <LoaderCircle size={14} className="entropy-spin" /> : <Trash2 size={14} />} Delete
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => setChecked(new Set())}
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
                                        aria-label="Select all workflows"
                                        checked={filtered.length > 0 && filtered.every((item) => checked.has(item.name))}
                                        ref={(element) => {
                                            if (element) {
                                                const count = filtered.filter((item) => checked.has(item.name)).length
                                                element.indeterminate = count > 0 && count < filtered.length
                                            }
                                        }}
                                        onChange={(event) =>
                                            setChecked(
                                                event.target.checked ? new Set(filtered.map((item) => item.name)) : new Set(),
                                            )
                                        }
                                        disabled={filtered.length === 0}
                                    />
                                </th>
                                <th scope="col">Workflow</th>
                                <th scope="col">Version</th>
                                <th scope="col">Updated</th>
                                <th scope="col" className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={5}>
                                        <EntropyLoader label={`Loading workflows…`} />
                                    </td>
                                </tr>
                            ) : filtered.length === 0 && newDrafts.length === 0 ? (
                                <tr>
                                    <td colSpan={5}>
                                        <div className="list-empty">
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
                                <>
                                {newDrafts.map((item) => (
                                    <tr key={`draft-${item.id}`} className="wf-draft-row">
                                        <td className="list-check-cell" />
                                        <td>
                                            <div className="list-name">
                                                <span className="list-name-icon is-warning" aria-hidden="true">
                                                    <FileWarning size={16} />
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>
                                                        {item.title}{' '}
                                                        <span className="list-chip list-chip-warning">Draft</span>
                                                    </strong>
                                                    <span>
                                                        Saved with {item.errors.length} problem
                                                        {item.errors.length === 1 ? '' : 's'} by {item.updated_by ?? 'someone'}; it
                                                        cannot run until fixed.
                                                    </span>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <span className="list-version">—</span>
                                        </td>
                                        <td className="list-cell-text">{formatDate(item.updated_at)}</td>
                                        <td>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Continue editing ${item.title}`}
                                                    title={editReason ?? 'Continue editing'}
                                                    aria-disabled={editReason ? true : undefined}
                                                    onClick={() => {
                                                        if (!editReason) setBuilder({ mode: 'draft', id: item.id, workflow: null })
                                                    }}
                                                >
                                                    <Pencil size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                    aria-label={`Discard draft ${item.title}`}
                                                    title={editReason ?? 'Discard draft'}
                                                    aria-disabled={editReason ? true : undefined}
                                                    onClick={() => {
                                                        if (!editReason) void discardDraft(item)
                                                    }}
                                                >
                                                    <Trash2 size={15} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {filtered.map((workflow) => (
                                    <tr
                                        key={workflow.name}
                                        className={selectedName === workflow.name ? 'is-selected' : undefined}
                                        aria-selected={selectedName === workflow.name}
                                        onClick={() => setSelectedName(workflow.name)}
                                    >
                                        <td className="list-check-cell" onClick={(event) => event.stopPropagation()}>
                                            <input
                                                type="checkbox"
                                                className="list-check"
                                                aria-label={`Select ${workflow.name}`}
                                                checked={checked.has(workflow.name)}
                                                onChange={() => toggleChecked(workflow.name)}
                                            />
                                        </td>
                                        <td>
                                            <div className="list-name">
                                                <span className="list-name-icon" aria-hidden="true">
                                                    <WorkflowIcon size={16} />
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>
                                                        {workflow.name}
                                                        {draftOf.has(workflow.name) && (
                                                            <>
                                                                {' '}
                                                                <span
                                                                    className="list-chip list-chip-warning"
                                                                    title="Has a version saved with errors; open it to continue"
                                                                >
                                                                    Draft
                                                                </span>
                                                            </>
                                                        )}
                                                    </strong>
                                                    <span>{workflow.description || 'No description'}</span>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <span className="list-version">{workflow.version}</span>
                                        </td>
                                        <td className="list-cell-text">{formatDate(workflow.updated_at)}</td>
                                        <td>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-primary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Run ${workflow.name}`}
                                                    title={runReason ?? 'Run'}
                                                    aria-disabled={runReason ? true : undefined}
                                                    onClick={() => {
                                                        if (!runReason) setRunning(workflow.name)
                                                    }}
                                                    disabled={deleting === workflow.name}
                                                >
                                                    <Play size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`${viewOnly ? 'View' : 'Edit'} ${workflow.name}`}
                                                    title={viewOnly ? 'View (read only)' : editReason ?? 'Edit'}
                                                    aria-disabled={editReason && !viewOnly ? true : undefined}
                                                    onClick={() => {
                                                        if (!editReason || viewOnly) setBuilder({ mode: 'edit', name: workflow.name })
                                                    }}
                                                    disabled={deleting === workflow.name}
                                                >
                                                    {viewOnly ? <Eye size={15} /> : <Pencil size={15} />}
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Alerts for ${workflow.name}`}
                                                    title="E-mail alerts"
                                                    onClick={() => setAlerting(workflow.name)}
                                                    disabled={deleting === workflow.name}
                                                >
                                                    <BellRing size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                    aria-label={`Delete ${workflow.name}`}
                                                    title={deleteReason ?? 'Delete'}
                                                    aria-disabled={deleteReason ? true : undefined}
                                                    onClick={() => {
                                                        if (!deleteReason) void remove(workflow)
                                                    }}
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
                                ))}
                                </>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            {deletePickerOpen && (
                <PickerDialog
                    title="Delete which workflow?"
                    subtitle="No workflow is selected. Choose the workflow to delete."
                    icon={<Trash2 size={18} />}
                    placeholder="Search workflows"
                    empty="No workflows match your search."
                    load={(query) =>
                        workflows
                            .filter((item) =>
                                `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase()),
                            )
                            .map((item) => ({
                                id: item.name,
                                label: item.name,
                                detail: item.description || `Version ${item.version}`,
                            }))
                    }
                    onPick={(item) => {
                        const workflow = workflows.find((entry) => entry.name === item.id)
                        if (workflow) void remove(workflow)
                    }}
                    onClose={() => setDeletePickerOpen(false)}
                />
            )}

            {running && <StartRunDialog kind="workflow" target={running} onClose={() => setRunning(null)} />}
            {moving && (
                <MoveToProjectDialog
                    kind="workflows"
                    workflows={moving}
                    labels={moving}
                    onClose={() => setMoving(null)}
                    onDone={() => {
                        setChecked(new Set())
                        refresh()
                    }}
                />
            )}
            {alerting && (
                <RunAlertsDialog
                    kind="workflow"
                    target={alerting}
                    name={alerting}
                    canEdit={!editReason}
                    onClose={() => setAlerting(null)}
                />
            )}

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
                            key={
                                builder.mode === 'edit'
                                    ? builder.name
                                    : builder.mode === 'draft'
                                      ? `draft-${builder.id}`
                                      : 'new'
                            }
                            name={
                                builder.mode === 'edit'
                                    ? builder.name
                                    : builder.mode === 'draft'
                                      ? builder.workflow ?? undefined
                                      : undefined
                            }
                            draftId={builder.mode === 'draft' ? builder.id : null}
                            onClose={() => setBuilder(null)}
                            onSaved={() => {
                                setBuilder(null)
                                refresh()
                            }}
                            readOnly={builder.mode === 'edit' && viewOnly}
                            restoreReason={restoreReason}
                        />
                    </Suspense>
                </AppPortal>
            )}
        </section>
    )
}
