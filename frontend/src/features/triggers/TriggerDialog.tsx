import { useEffect, useMemo, useState } from 'react'
import { LoaderCircle, Webhook } from 'lucide-react'

import { pluginsApi, type PluginContract } from '../../api/plugins.api'
import { nodesApi, type EntropyNode } from '../../api/runs.api'
import { triggersApi, type Trigger, type TriggerInput, type TriggerSource } from '../../api/triggers.api'
import { workflowsApi, type WorkflowSummary } from '../../api/workflows.api'
import { useErrorToast } from '../../components/feedback/useToast'
import Dialog from '../../components/layout/Dialog'
import ParamsEditor from '../runs/ParamsEditor'
import { parseRows, rowsFor, type ParamRow } from '../runs/params'
import { errorMessage } from '../runs/format'

/** Create or change a trigger; a new webhook's token comes back in `onSaved`. */
export default function TriggerDialog({
    trigger,
    onClose,
    onSaved,
}: {
    trigger: Trigger | null
    onClose: () => void
    onSaved: (trigger: Trigger, token: string | null) => void
}) {
    const [name, setName] = useState(trigger?.name ?? '')
    const [description, setDescription] = useState(trigger?.description ?? '')
    const [source, setSource] = useState<TriggerSource>(trigger?.source ?? 'webhook')
    const [destination, setDestination] = useState(trigger?.destination ?? '/queue/')
    const [kind, setKind] = useState<'workflow' | 'plugin'>(trigger?.kind ?? 'workflow')
    const [target, setTarget] = useState(trigger?.target ?? '')
    const [node, setNode] = useState(trigger?.node ?? 'local')
    const [usePayload, setUsePayload] = useState(trigger?.use_payload ?? true)
    const [enabled, setEnabled] = useState(trigger?.enabled ?? true)
    const [rows, setRows] = useState<ParamRow[]>([])

    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
    const [plugins, setPlugins] = useState<PluginContract[]>([])
    const [nodes, setNodes] = useState<EntropyNode[]>([])
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)

    useEffect(() => {
        let active = true
        Promise.all([
            workflowsApi.list().catch(() => ({ items: [] as WorkflowSummary[] })),
            pluginsApi.contracts().catch(() => ({ items: [] as PluginContract[] })),
            nodesApi.list().catch(() => ({ items: [] as EntropyNode[] })),
        ]).then(([workflowList, pluginList, nodeList]) => {
            if (!active) return
            setWorkflows(workflowList.items)
            setPlugins(pluginList.items)
            setNodes(nodeList.items)
        })
        return () => {
            active = false
        }
    }, [])

    // Plugin arguments come from its contract; workflow variables are free-form.
    const specs = useMemo(
        () => (kind === 'plugin' ? plugins.find((item) => item.qualified_name === target)?.arguments ?? [] : []),
        [kind, plugins, target],
    )
    const specKey = specs.map((spec) => spec.name).join(',')

    useEffect(() => {
        const timer = setTimeout(() => {
            setRows((current) => {
                const existing = current.length
                    ? parseRows(current.map((row) => ({ ...row, spec: undefined }))).values
                    : (trigger?.parameters ?? {})
                return rowsFor(specs, existing)
            })
        }, 0)
        return () => clearTimeout(timer)
        // Rebuild only when the target's argument list changes.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [specKey])

    const targets =
        kind === 'workflow'
            ? workflows.map((item) => item.name)
            : plugins.map((item) => item.qualified_name)

    const save = async () => {
        const parsed = parseRows(rows)
        if (parsed.error) {
            setError(parsed.error)
            return
        }
        if (!target) {
            setError(`Choose a ${kind} to run.`)
            return
        }
        const values: TriggerInput = {
            name: name.trim(),
            description: description.trim(),
            source,
            kind,
            target,
            node,
            parameters: parsed.values,
            use_payload: usePayload,
            destination: source === 'queue' ? destination.trim() : null,
            enabled,
        }
        setSaving(true)
        setError(null)
        try {
            const result = trigger ? await triggersApi.update(trigger.id, values) : await triggersApi.create(values)
            onSaved(result.trigger, result.token)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to save the trigger.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={trigger ? `Edit ${trigger.name}` : 'New trigger'}
            subtitle="Runs a workflow or plugin when its webhook is called or a message arrives on a queue, as you."
            icon={<Webhook size={18} />}
            onClose={onClose}
            className="schedule-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => void save()}
                        disabled={saving || !name.trim()}
                    >
                        {saving && <LoaderCircle size={15} className="entropy-spin" />}
                        {trigger ? 'Save changes' : 'Create trigger'}
                    </button>
                </>
            }
        >
            <div className="admin-form-grid">
                <label className="admin-field">
                    <span>Name</span>
                    <input value={name} onChange={(event) => setName(event.target.value)} maxLength={80} />
                </label>
                <label className="admin-field">
                    <span>Description</span>
                    <input
                        value={description}
                        onChange={(event) => setDescription(event.target.value)}
                        placeholder="Optional"
                        maxLength={500}
                    />
                </label>

                <label className="admin-field">
                    <span>Fired by</span>
                    <select className="schedule-select" value={source} onChange={(event) => setSource(event.target.value as TriggerSource)}>
                        <option value="webhook">A webhook (HTTP POST)</option>
                        <option value="queue">A queue message (STOMP)</option>
                    </select>
                </label>
                {source === 'queue' ? (
                    <label className="admin-field">
                        <span>Destination</span>
                        <input
                            value={destination}
                            onChange={(event) => setDestination(event.target.value)}
                            placeholder="/queue/deploy.orders"
                            spellCheck={false}
                            maxLength={210}
                        />
                        <small>A /queue/… or /topic/… on the broker in Administration → Settings → Message queue.</small>
                    </label>
                ) : (
                    <div className="admin-field">
                        <span>Address</span>
                        <small className="trigger-hint">
                            {trigger?.hook_url
                                ? trigger.hook_url
                                : 'Its address and secret token are shown once the trigger is created.'}
                        </small>
                    </div>
                )}

                <label className="admin-field">
                    <span>Runs a</span>
                    <select
                        className="schedule-select"
                        value={kind}
                        onChange={(event) => {
                            setKind(event.target.value as 'workflow' | 'plugin')
                            setTarget('')
                        }}
                    >
                        <option value="workflow">Workflow</option>
                        <option value="plugin">Plugin</option>
                    </select>
                </label>
                <label className="admin-field">
                    <span>{kind === 'workflow' ? 'Workflow' : 'Plugin'}</span>
                    <select className="schedule-select" value={target} onChange={(event) => setTarget(event.target.value)}>
                        <option value="">Choose…</option>
                        {targets.map((item) => (
                            <option key={item} value={item}>
                                {item}
                            </option>
                        ))}
                        {target && !targets.includes(target) && <option value={target}>{target} (missing)</option>}
                    </select>
                </label>

                <label className="admin-field">
                    <span>Runner node</span>
                    <select className="schedule-select" value={node} onChange={(event) => setNode(event.target.value)}>
                        {(nodes.length ? nodes : [{ name: 'local' } as EntropyNode]).map((item) => (
                            <option key={item.name} value={item.name}>
                                {item.name}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="admin-field schedule-enabled">
                    <span>Status</span>
                    <span className="schedule-switch">
                        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
                        {enabled ? 'Enabled' : 'Paused'}
                    </span>
                </label>

                <label className="admin-field admin-field-wide schedule-enabled">
                    <span>Payload</span>
                    <span className="schedule-switch">
                        <input type="checkbox" checked={usePayload} onChange={(event) => setUsePayload(event.target.checked)} />
                        A JSON object payload overrides the {kind === 'workflow' ? 'variables' : 'arguments'} below, key by key
                    </span>
                    <small>
                        {kind === 'workflow'
                            ? 'The workflow also gets trigger_payload (the whole payload), trigger_name and trigger_source.'
                            : 'Only keys the plugin declares as arguments are used; others are ignored.'}
                    </small>
                </label>

                <div className="admin-field admin-field-wide">
                    <span>{kind === 'workflow' ? 'Variables' : 'Arguments'}</span>
                    <ParamsEditor
                        rows={rows}
                        onChange={setRows}
                        emptyText={kind === 'workflow' ? 'Uses the workflow’s own variables.' : 'No arguments.'}
                        addLabel={kind === 'workflow' ? 'Override a variable' : 'Add argument'}
                    />
                </div>
            </div>
        </Dialog>
    )
}
