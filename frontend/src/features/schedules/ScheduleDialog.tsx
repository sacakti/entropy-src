import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CalendarClock, CheckCircle2, LoaderCircle } from 'lucide-react'

import { pluginsApi, type PluginContract } from '../../api/plugins.api'
import {
    nodesApi,
    schedulesApi,
    type EntropyNode,
    type Schedule,
    type ScheduleInput,
} from '../../api/runs.api'
import { workflowsApi, type WorkflowSummary } from '../../api/workflows.api'
import Dialog from '../../components/layout/Dialog'
import ParamsEditor from '../runs/ParamsEditor'
import { parseRows, rowsFor, type ParamRow } from '../runs/params'
import { errorMessage, formatDateTime } from '../runs/format'
import { useErrorToast } from '../../components/feedback/useToast'

const PRESETS = [
    { label: 'Every 5 minutes', cron: '*/5 * * * *' },
    { label: 'Hourly', cron: '0 * * * *' },
    { label: 'Daily 02:00', cron: '0 2 * * *' },
    { label: 'Weekdays 09:00', cron: '0 9 * * 1-5' },
    { label: 'Mondays 06:00', cron: '0 6 * * 1' },
    { label: 'Monthly', cron: '0 0 1 * *' },
]

function browserTimeZone(): string {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    } catch {
        return 'UTC'
    }
}

function timeZones(current: string): string[] {
    const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
    const zones = intl.supportedValuesOf?.('timeZone') ?? []
    return Array.from(new Set(['UTC', current, ...zones]))
}

type Preview = { valid: boolean; error: string | null; next: string[] } | null

export default function ScheduleDialog({
    schedule,
    onClose,
    onSaved,
}: {
    schedule: Schedule | null
    onClose: () => void
    onSaved: (schedule: Schedule) => void
}) {
    const [name, setName] = useState(schedule?.name ?? '')
    const [description, setDescription] = useState(schedule?.description ?? '')
    const [kind, setKind] = useState<'workflow' | 'plugin'>(schedule?.kind ?? 'workflow')
    const [target, setTarget] = useState(schedule?.target ?? '')
    const [cron, setCron] = useState(schedule?.cron ?? '0 2 * * *')
    const [zone, setZone] = useState(schedule?.timezone ?? browserTimeZone())
    const [node, setNode] = useState(schedule?.node ?? 'local')
    const [enabled, setEnabled] = useState(schedule?.enabled ?? true)
    const [rows, setRows] = useState<ParamRow[]>([])

    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
    const [plugins, setPlugins] = useState<PluginContract[]>([])
    const [nodes, setNodes] = useState<EntropyNode[]>([])
    const [preview, setPreview] = useState<Preview>(null)
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
                    : (schedule?.parameters ?? {})
                return rowsFor(specs, existing)
            })
        }, 0)
        return () => clearTimeout(timer)
        // Rebuild only when the target's argument list changes.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [specKey])

    useEffect(() => {
        let active = true
        const timer = setTimeout(() => {
            schedulesApi
                .preview(cron, zone)
                .then((result) => {
                    if (active) setPreview(result)
                })
                .catch(() => undefined)
        }, 300)
        return () => {
            active = false
            clearTimeout(timer)
        }
    }, [cron, zone])

    const targets =
        kind === 'workflow'
            ? workflows.map((item) => ({ value: item.name, label: item.name }))
            : plugins.map((item) => ({ value: item.qualified_name, label: item.qualified_name }))

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

        const values: ScheduleInput = {
            name: name.trim(),
            description: description.trim(),
            kind,
            target,
            cron,
            timezone: zone,
            node,
            parameters: parsed.values,
            enabled,
        }

        setSaving(true)
        setError(null)
        try {
            const result = schedule
                ? await schedulesApi.update(schedule.id, values)
                : await schedulesApi.create(values)
            onSaved(result.schedule)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to save the schedule.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={schedule ? `Edit ${schedule.name}` : 'New schedule'}
            subtitle="Runs a workflow or plugin on a cron schedule, as you."
            icon={<CalendarClock size={18} />}
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
                        disabled={saving || !name.trim() || preview?.valid === false}
                    >
                        {saving && <LoaderCircle size={15} className="entropy-spin" />}
                        {schedule ? 'Save changes' : 'Create schedule'}
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
                    <select
                        className="schedule-select"
                        value={target}
                        onChange={(event) => setTarget(event.target.value)}
                    >
                        <option value="">Choose…</option>
                        {targets.map((item) => (
                            <option key={item.value} value={item.value}>
                                {item.label}
                            </option>
                        ))}
                        {target && !targets.some((item) => item.value === target) && (
                            <option value={target}>{target} (missing)</option>
                        )}
                    </select>
                </label>

                <label className="admin-field">
                    <span>Cron expression</span>
                    <input
                        className="schedule-cron"
                        value={cron}
                        onChange={(event) => setCron(event.target.value)}
                        spellCheck={false}
                        placeholder="minute hour day month weekday"
                    />
                </label>
                <label className="admin-field">
                    <span>Time zone</span>
                    <select className="schedule-select" value={zone} onChange={(event) => setZone(event.target.value)}>
                        {timeZones(zone).map((item) => (
                            <option key={item} value={item}>
                                {item}
                            </option>
                        ))}
                    </select>
                </label>

                <div className="admin-field admin-field-wide">
                    <div className="schedule-presets" aria-label="Common schedules">
                        {PRESETS.map((preset) => (
                            <button
                                key={preset.cron}
                                type="button"
                                className={`schedule-preset${cron === preset.cron ? ' is-active' : ''}`}
                                onClick={() => setCron(preset.cron)}
                            >
                                {preset.label}
                            </button>
                        ))}
                    </div>
                    <div className={`schedule-preview${preview?.valid === false ? ' is-invalid' : ''}`} role="status">
                        {preview === null ? (
                            <span>Checking…</span>
                        ) : preview.valid ? (
                            <>
                                <CheckCircle2 size={14} />
                                <span>
                                    Next:{' '}
                                    {preview.next.length
                                        ? preview.next.slice(0, 3).map(formatDateTime).join(' · ')
                                        : 'never (no matching date)'}
                                </span>
                            </>
                        ) : (
                            <>
                                <AlertCircle size={14} />
                                <span>{preview.error}</span>
                            </>
                        )}
                    </div>
                </div>

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
                        <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(event) => setEnabled(event.target.checked)}
                        />
                        {enabled ? 'Enabled' : 'Paused'}
                    </span>
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
