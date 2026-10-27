import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    ArrowLeft,
    CheckCircle2,
    Columns2,
    FileWarning,
    History,
    LoaderCircle,
    Rows2,
    Save,
    ShieldCheck,
    TriangleAlert,
    X,
} from 'lucide-react'

import WallpaperLayer from '../../preferences/WallpaperLayer'
import '../../../styles/workflow-builder.css'
import { listPlugins, pluginsApi, type PluginContract } from '../../../api/plugins.api'
import { loadVaultKeys } from '../../vault/vaultKeys'
import {
    workflowDraftsApi,
    workflowsApi,
    type WorkflowDraftSummary,
    type WorkflowFormat,
} from '../../../api/workflows.api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { useShortcuts } from '../../../components/layout/useShortcuts'
import HistoryDialog from '../../history/HistoryDialog'
import DiffView from '../../plugins/editor/DiffView'
import CodeView from './CodeView'
import FormView from './FormView'
import {
    definitionFromState,
    emptyState,
    parse,
    serialize,
    stateFromDefinition,
    validateState,
    type BuilderState,
    type CodeFormat,
    type Issue,
    type ParseFailure,
} from './model'
import EntropyLoader from '../../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../../components/feedback/useToast'

type View = 'form' | CodeFormat

function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

/** Installed plugins without argument details, from the paginated list API. */
async function loadPluginsWithoutContracts(): Promise<PluginContract[]> {
    const plugins: PluginContract[] = []

    for (let page = 1; ; page += 1) {
        const result = await listPlugins({ page, page_size: 10 })

        plugins.push(
            ...result.items.map((item) => ({ ...item, description: null, arguments: [], outputs: [] })),
        )

        if (page >= result.pagination.total_pages) return plugins
    }
}

export default function WorkflowBuilder({
    name,
    onClose,
    onSaved,
    readOnly = false,
    restoreReason = null,
    draftId = null,
}: {
    /** Name of the workflow to edit; omit to create a new one. */
    name?: string
    /** Open this draft (saved with errors) instead of the registered definition. */
    draftId?: number | null
    onClose: () => void
    onSaved: (name: string) => void
    /** View the definition without changing it (read access only). */
    readOnly?: boolean
    /** Why earlier versions may not be restored, or null when they may. */
    restoreReason?: string | null
}) {
    const { notify, modal } = useFeedback()
    const editing = name !== undefined

    const [loading, setLoading] = useState(true)
    const [historyOpen, setHistoryOpen] = useState(false)
    // Bumped to load the workflow again, e.g. after restoring a version.
    const [reload, setReload] = useState(0)
    const [loadError, setLoadError] = useState<string | null>(null)
    useErrorToast(loadError)
    const [contracts, setContracts] = useState<PluginContract[]>([])
    const [vaultKeys, setVaultKeys] = useState<string[]>([])
    const [contractsError, setContractsError] = useState<string | null>(null)

    const [view, setView] = useState<View>('form')
    const [form, setForm] = useState<BuilderState>(emptyState)
    const [code, setCode] = useState('')
    const [initial, setInitial] = useState('')

    const [busy, setBusy] = useState<'save' | 'validate' | null>(null)
    // Saving goes through a review of the changes (Save button or Ctrl+S).
    const [reviewing, setReviewing] = useState(false)
    const [sideBySide, setSideBySide] = useState(true)
    const [serverResult, setServerResult] = useState<{ ok: boolean; message: string } | null>(null)
    // The draft being edited (saved with errors), if any.
    const [draft, setDraft] = useState<WorkflowDraftSummary | null>(null)
    // A draft of this workflow that was not opened; offered in a banner.
    const [pendingDraft, setPendingDraft] = useState<WorkflowDraftSummary | null>(null)
    const [draftText, setDraftText] = useState('')

    const theme = useMemo(
        () =>
            document.documentElement.dataset.theme === 'light' ? 'entropy-light' : 'entropy-dark',
        [],
    )

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    useEffect(() => {
        let active = true

        // Contracts only enrich the form (typed arguments, outputs); a server
        // without them still lets workflows be built with custom arguments.
        Promise.all([
            pluginsApi.contracts().catch((error: unknown) => {
                if (active) {
                    setContractsError(
                        errorMessage(error, 'Plugin arguments and outputs could not be loaded.'),
                    )
                }
                return loadPluginsWithoutContracts()
                    .catch(() => [] as PluginContract[])
                    .then((items) => ({ items }))
            }),
            loadVaultKeys(),
            editing ? workflowsApi.get(name, 'json') : Promise.resolve(null),
            draftId !== null ? workflowDraftsApi.get(draftId) : Promise.resolve(null),
            editing && draftId === null && !readOnly
                ? workflowDraftsApi.list().catch(() => ({ items: [] as WorkflowDraftSummary[] }))
                : Promise.resolve({ items: [] as WorkflowDraftSummary[] }),
        ])
            .then(([contractList, keys, workflow, openedDraft, drafts]) => {
                if (!active) return

                const state = workflow
                    ? stateFromDefinition(JSON.parse(workflow.definition))
                    : emptyState()

                setContracts(contractList.items)
                setVaultKeys(keys)
                setForm(state)
                setInitial(workflow ? JSON.stringify(definitionFromState(state)) : '')
                if (openedDraft) {
                    // A draft may not parse, so it opens as text in its own format.
                    setDraft(openedDraft)
                    setDraftText(openedDraft.definition)
                    setCode(openedDraft.definition)
                    setView(openedDraft.format)
                } else {
                    setPendingDraft(drafts.items.find((item) => item.workflow === name) ?? null)
                }
            })
            .catch((error: unknown) => {
                if (active) setLoadError(errorMessage(error, 'Unable to open the workflow.'))
            })
            .finally(() => {
                if (active) setLoading(false)
            })

        return () => {
            active = false
        }
    }, [draftId, editing, name, readOnly, reload])

    // ------------------------------------------------------------------
    // Current definition
    // ------------------------------------------------------------------

    const codeParse = useMemo(
        () => (view === 'form' ? null : parse(code, view)),
        [code, view],
    )
    const parseFailure: ParseFailure | null =
        codeParse && 'failure' in codeParse ? codeParse.failure : null

    /** The state the form would show for the current view, or null if code does not parse. */
    const currentState = useMemo((): BuilderState | null => {
        if (view === 'form') return form
        if (!codeParse || 'failure' in codeParse) return null

        try {
            return stateFromDefinition(codeParse.value)
        } catch {
            return null
        }
    }, [codeParse, form, view])

    const contractMap = useMemo(
        () => new Map(contracts.map((contract) => [contract.qualified_name, contract])),
        [contracts],
    )

    const issues: Issue[] = useMemo(() => {
        if (currentState) return validateState(currentState, contractMap)
        if (parseFailure) return [{ severity: 'error', message: 'Fix the syntax error before saving.' }]
        return [{ severity: 'error', message: 'The definition must be an object.' }]
    }, [contractMap, currentState, parseFailure])

    const errors = issues.filter((issue) => issue.severity === 'error')
    const warnings = issues.filter((issue) => issue.severity === 'warning')

    const currentDefinitionJson = useMemo(() => {
        if (view === 'form') return JSON.stringify(definitionFromState(form))
        return codeParse && 'value' in codeParse ? JSON.stringify(codeParse.value) : null
    }, [codeParse, form, view])

    // A draft may not parse; it is unchanged while its text is as it was opened.
    const dirty = draft
        ? !(view === draft.format && code === draftText)
        : currentDefinitionJson !== initial

    // ------------------------------------------------------------------
    // View switching
    // ------------------------------------------------------------------

    const switchView = (next: View) => {
        if (next === view) return

        if (view === 'form') {
            setCode(serialize(definitionFromState(form), next as CodeFormat))
            setView(next)
            return
        }

        if (!codeParse || 'failure' in codeParse) {
            notify.error('Fix the syntax error first; the definition cannot be converted.', {
                title: `Invalid ${view.toUpperCase()}`,
            })
            return
        }

        if (next === 'form') {
            try {
                setForm(stateFromDefinition(codeParse.value))
                setView('form')
            } catch (error) {
                notify.error(errorMessage(error, 'The definition cannot be shown as a form.'))
            }
            return
        }

        setCode(serialize(codeParse.value, next))
        setView(next)
    }

    // ------------------------------------------------------------------
    // Save / validate / cancel
    // ------------------------------------------------------------------

    const payload = (): { definition: string; format: WorkflowFormat } | null => {
        if (view === 'form') return { definition: serialize(definitionFromState(form), 'json'), format: 'json' }
        return parseFailure ? null : { definition: code, format: view }
    }

    const validateOnServer = async () => {
        const body = payload()
        if (!body) return

        setBusy('validate')

        try {
            const result = await workflowsApi.validate(body)
            setServerResult({
                ok: true,
                message: `Entropy accepts '${result.workflow.name}' with ${result.workflow.step_count} step${
                    result.workflow.step_count === 1 ? '' : 's'
                }.`,
            })
        } catch (error) {
            setServerResult({ ok: false, message: errorMessage(error, 'Validation failed.') })
        } finally {
            setBusy(null)
        }
    }

    const save = useCallback(async () => {
        if (busy) return

        if (errors.length > 0) {
            notify.error(`Fix ${errors.length} problem${errors.length === 1 ? '' : 's'} before saving.`, {
                title: 'Workflow not saved',
            })
            return
        }

        const body = view === 'form'
            ? { definition: serialize(definitionFromState(form), 'json'), format: 'json' as const }
            : { definition: code, format: view }

        setBusy('save')
        setServerResult(null)

        try {
            const saved = editing
                ? await workflowsApi.update(name, body)
                : await workflowsApi.create(body)

            // The server drops drafts of a saved workflow; a new one's goes by id.
            if (draft && !draft.workflow) await workflowDraftsApi.delete(draft.id).catch(() => undefined)
            notify.success(`Workflow '${saved.name}' saved as version ${saved.version}.`, { title: 'Workflow saved' })
            onSaved(saved.name)
        } catch (error) {
            setServerResult({ ok: false, message: errorMessage(error, 'Unable to save the workflow.') })
        } finally {
            setBusy(null)
        }
    }, [busy, code, draft, editing, errors.length, form, name, notify, onSaved, view])

    /** Keep the definition as it is, problems and all; it cannot run until fixed. */
    const saveWithErrors = async () => {
        if (busy) return

        const body =
            view === 'form'
                ? { definition: serialize(definitionFromState(form), 'json'), format: 'json' as const }
                : { definition: code, format: view }
        const problems = errors.map((issue) => issue.message)
        if (serverResult && !serverResult.ok) problems.push(serverResult.message)

        setBusy('save')
        try {
            const saved = await workflowDraftsApi.save({
                id: draft?.id ?? pendingDraft?.id ?? null,
                workflow: editing ? name : null,
                errors: problems,
                ...body,
            })
            notify.success(
                saved.errors.length > 0
                    ? `Saved '${saved.title}' with ${saved.errors.length} problem${saved.errors.length === 1 ? '' : 's'}. It cannot run until they are fixed.`
                    : `Saved '${saved.title}' as a draft.`,
                { title: 'Draft saved' },
            )
            onSaved(saved.title)
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to save the draft.'), { title: 'Draft not saved' })
        } finally {
            setBusy(null)
        }
    }

    const openPendingDraft = async () => {
        if (!pendingDraft) return
        try {
            const opened = await workflowDraftsApi.get(pendingDraft.id)
            setDraft(opened)
            setDraftText(opened.definition)
            setPendingDraft(null)
            setCode(opened.definition)
            setView(opened.format)
            setServerResult(null)
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to open the draft.'))
        }
    }

    const discardDraft = async (target: WorkflowDraftSummary) => {
        const confirmed = await modal.confirm({
            title: 'Discard the draft?',
            message: `The version saved with errors on ${new Date(target.updated_at).toLocaleString()} is deleted.`,
            confirmText: 'Discard draft',
            cancelText: 'Keep it',
            destructive: true,
        })
        if (!confirmed) return
        try {
            await workflowDraftsApi.delete(target.id)
            if (draft?.id === target.id) {
                notify.success('Draft discarded.')
                onSaved(target.title)
                return
            }
            setPendingDraft(null)
            notify.success('Draft discarded.')
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to discard the draft.'))
        }
    }

    const canSaveWithErrors = errors.length > 0 || (serverResult !== null && !serverResult.ok)

    const requestSave = () => {
        if (busy) return

        if (errors.length > 0) {
            notify.error(
                `Fix ${errors.length} problem${errors.length === 1 ? '' : 's'} before saving, or use Save with errors to keep it as a draft.`,
                { title: 'Workflow not saved' },
            )
            return
        }

        if (editing && !dirty && !draft) {
            notify.info('There are no changes to save.')
            return
        }

        setReviewing(true)
    }

    // Both sides as YAML, so the review reads the same whichever view was used.
    const reviewTexts = useMemo(() => {
        if (!reviewing) return null

        const original = initial ? serialize(JSON.parse(initial), 'yaml') : ''
        const modified = currentDefinitionJson ? serialize(JSON.parse(currentDefinitionJson), 'yaml') : ''

        return { original, modified }
    }, [currentDefinitionJson, initial, reviewing])

    useShortcuts(
        {
            'mod+s': () => {
                if (readOnly) return
                if (reviewing) void save()
                else requestSave()
            },
        },
        !loading && !loadError,
    )

    const cancel = async () => {
        if (
            dirty &&
            !(await modal.confirm({
                title: 'Discard unsaved changes?',
                message: 'Your changes to this workflow will be lost.',
                confirmText: 'Discard',
                cancelText: 'Keep editing',
                destructive: true,
            }))
        ) {
            return
        }

        onClose()
    }

    useEffect(() => {
        if (!dirty) return

        const warn = (event: BeforeUnloadEvent) => event.preventDefault()
        window.addEventListener('beforeunload', warn)
        return () => window.removeEventListener('beforeunload', warn)
    }, [dirty])

    // ------------------------------------------------------------------
    // Render
    // ------------------------------------------------------------------

    return (
        <div className="wf-builder" role="dialog" aria-modal="true" aria-label="Workflow builder">
            <WallpaperLayer veil="var(--app-bg)" />
            <header className="wf-builder-topbar">
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary"
                    onClick={() => void cancel()}
                    disabled={busy === 'save'}
                >
                    <X size={16} />
                    {readOnly ? 'Close' : 'Cancel'}
                </button>

                <div className="wf-builder-title">
                    <strong>{editing ? name : draft ? draft.title : 'New workflow'}</strong>
                    {readOnly && <span className="wf-chip">Read only</span>}
                    {draft && (
                        <span className="wf-chip wf-chip-warning" title="Saved with errors; it cannot run until fixed">
                            Draft
                        </span>
                    )}
                    {dirty && !loading && !readOnly && <span className="wf-chip wf-chip-warning">Unsaved</span>}
                </div>

                <div className="wf-builder-actions">
                    <div className="wf-segmented" role="tablist" aria-label="Editor view">
                        {(['form', 'json', 'yaml'] as View[]).map((option) => (
                            <button
                                key={option}
                                type="button"
                                role="tab"
                                aria-selected={view === option}
                                className={view === option ? 'is-active' : ''}
                                onClick={() => switchView(option)}
                                disabled={loading || !!loadError}
                            >
                                {option === 'form' ? 'Form' : option.toUpperCase()}
                            </button>
                        ))}
                    </div>

                    {editing && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            onClick={() => setHistoryOpen(true)}
                            disabled={loading || !!loadError || busy !== null}
                            title="Earlier versions of this workflow: compare and restore"
                        >
                            <History size={15} />
                            History
                        </button>
                    )}

                    {!readOnly && (
                    <>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => void validateOnServer()}
                        disabled={loading || !!loadError || busy !== null || !!parseFailure}
                        title="Check the definition with Entropy's workflow validator"
                    >
                        {busy === 'validate' ? (
                            <LoaderCircle size={15} className="entropy-spin" />
                        ) : (
                            <ShieldCheck size={15} />
                        )}
                        Validate
                    </button>

                    {(canSaveWithErrors || draft) && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            onClick={() => void saveWithErrors()}
                            disabled={loading || !!loadError || busy !== null || reviewing}
                            title="Keep the workflow as a draft with its problems; it cannot run until they are fixed"
                        >
                            <FileWarning size={15} />
                            Save with errors
                        </button>
                    )}

                    {draft && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-danger-quiet"
                            onClick={() => void discardDraft(draft)}
                            disabled={busy !== null}
                        >
                            Discard draft
                        </button>
                    )}

                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={requestSave}
                        disabled={loading || !!loadError || busy !== null || reviewing || (editing && !dirty && !draft)}
                        title="Review changes, then save (Ctrl+S)"
                    >
                        {busy === 'save' ? (
                            <LoaderCircle size={15} className="entropy-spin" />
                        ) : (
                            <Save size={15} />
                        )}
                        {editing ? 'Save' : 'Create'}
                    </button>
                    </>
                    )}
                </div>
            </header>

            {historyOpen && name && (
                <HistoryDialog
                    kind="workflow"
                    name={name}
                    restoreReason={
                        restoreReason ?? (dirty ? 'Save or discard your unsaved changes before restoring.' : null)
                    }
                    onRestored={() => setReload((value) => value + 1)}
                    onClose={() => setHistoryOpen(false)}
                />
            )}

            {(serverResult || contractsError || errors.length > 0 || warnings.length > 0 || pendingDraft) &&
                !loading &&
                !loadError && (
                <div className="wf-builder-banner">
                    {pendingDraft && (
                        <div className="entropy-alert entropy-alert-warning wf-draft-banner" role="status">
                            <FileWarning size={15} />
                            <span>
                                A version saved with errors exists ({pendingDraft.errors.length} problem
                                {pendingDraft.errors.length === 1 ? '' : 's'}, by {pendingDraft.updated_by ?? 'someone'}
                                {' on '}
                                {new Date(pendingDraft.updated_at).toLocaleString()}).
                            </span>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => void openPendingDraft()}
                            >
                                Open draft
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={() => void discardDraft(pendingDraft)}
                            >
                                Discard
                            </button>
                        </div>
                    )}
                    {contractsError && (
                        <div className="entropy-alert entropy-alert-warning" role="status">
                            <TriangleAlert size={15} />
                            <span>
                                Plugin arguments are unavailable, so steps use custom arguments only.{' '}
                                {contractsError}
                            </span>
                        </div>
                    )}
                    {serverResult && (
                        <div
                            className={`entropy-alert ${serverResult.ok ? 'entropy-alert-success' : 'entropy-alert-error'}`}
                            role={serverResult.ok ? 'status' : 'alert'}
                        >
                            {serverResult.ok ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
                            <span>{serverResult.message}</span>
                        </div>
                    )}
                    {(errors.length > 0 || warnings.length > 0) && (
                        <details className="wf-problems" open={errors.length > 0 && errors.length <= 4}>
                            <summary>
                                {errors.length > 0 && (
                                    <span className="wf-problems-count is-error">
                                        <AlertCircle size={13} /> {errors.length} error{errors.length === 1 ? '' : 's'}
                                    </span>
                                )}
                                {warnings.length > 0 && (
                                    <span className="wf-problems-count is-warning">
                                        <TriangleAlert size={13} /> {warnings.length} warning
                                        {warnings.length === 1 ? '' : 's'}
                                    </span>
                                )}
                            </summary>
                            <ul>
                                {[...errors, ...warnings].map((issue) => (
                                    <li key={`${issue.target}-${issue.message}`} className={`is-${issue.severity}`}>
                                        {issue.message}
                                    </li>
                                ))}
                            </ul>
                        </details>
                    )}
                </div>
            )}

            <div className="wf-builder-body">
                {loading ? (
                    <EntropyLoader label={`Loading plugins${editing ? ' and workflow' : ''}…`} />
                ) : loadError ? (
                    <div className="wf-builder-state">
                        <p className="entropy-unavailable">Not available.</p>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Close
                        </button>
                    </div>
                ) : reviewing && reviewTexts ? (
                    <section className="wf-review" aria-label="Review changes">
                        <header className="wf-review-header">
                            <div>
                                <strong>Review changes</strong>
                                <span>
                                    {editing
                                        ? 'Saved definition on the left, your changes on the right (YAML).'
                                        : 'The new workflow definition (YAML).'}
                                </span>
                            </div>
                            <div className="wf-review-actions">
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-sm"
                                    onClick={() => setSideBySide((value) => !value)}
                                >
                                    {sideBySide ? <Rows2 size={14} /> : <Columns2 size={14} />}
                                    {sideBySide ? 'Inline' : 'Side by side'}
                                </button>
                            </div>
                        </header>
                        <div className="wf-review-diff">
                            <DiffView
                                original={reviewTexts.original}
                                modified={reviewTexts.modified}
                                language="yaml"
                                theme={theme}
                                sideBySide={sideBySide}
                            />
                        </div>
                        <footer className="wf-review-footer">
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary"
                                onClick={() => setReviewing(false)}
                                disabled={busy === 'save'}
                            >
                                <ArrowLeft size={15} />
                                Back to editor
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-primary"
                                onClick={() => void save()}
                                disabled={busy !== null}
                            >
                                {busy === 'save' ? (
                                    <LoaderCircle size={15} className="entropy-spin" />
                                ) : (
                                    <Save size={15} />
                                )}
                                {editing ? 'Confirm & save' : 'Confirm & create'}
                            </button>
                        </footer>
                    </section>
                ) : view === 'form' ? (
                    // A disabled fieldset makes every control of the form read-only.
                    <fieldset className="wf-form-fieldset" disabled={readOnly}>
                        <FormView
                            state={form}
                            onChange={(next) => {
                                setForm(next)
                                setServerResult(null)
                            }}
                            contracts={contracts}
                            vaultKeys={vaultKeys}
                            issues={issues}
                            editing={editing}
                        />
                    </fieldset>
                ) : (
                    <CodeView
                        text={code}
                        format={view}
                        failure={parseFailure}
                        theme={theme}
                        onChange={(text) => {
                            setCode(text)
                            setServerResult(null)
                        }}
                        onSaveShortcut={requestSave}
                        readOnly={readOnly}
                    />
                )}
            </div>
        </div>
    )
}
