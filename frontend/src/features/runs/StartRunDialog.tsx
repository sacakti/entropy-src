import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, LoaderCircle, Play, Server } from 'lucide-react'

import { pluginsApi } from '../../api/plugins.api'
import { nodesApi, runsApi, type EntropyNode } from '../../api/runs.api'
import { workflowsApi } from '../../api/workflows.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from './format'
import { openRun } from './navigation'
import ParamsEditor from './ParamsEditor'
import RunAdvancedOptions from './RunAdvancedOptions'
import { EMPTY_ADVANCED, runOptionsFor, type AdvancedState, type PlanCheck } from './runOptions'
import { parseRows, rowsFor, type ParamRow } from './params'

type Check = { state: 'checking' } | { state: 'valid'; summary: string } | { state: 'invalid'; error: string }

/**
 * Validate a workflow (or plugin), pick the node to run on, review the
 * inputs and start it; then follow the run live.
 */
export default function StartRunDialog({
    kind,
    target,
    onClose,
}: {
    kind: 'workflow' | 'plugin'
    target: string
    onClose: () => void
}) {
    const { notify } = useFeedback()
    const [nodes, setNodes] = useState<EntropyNode[]>([])
    const [node, setNode] = useState('local')
    const [rows, setRows] = useState<ParamRow[]>([])
    const [check, setCheck] = useState<Check>({ state: 'checking' })
    const [starting, setStarting] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [nodesLoaded, setNodesLoaded] = useState(false)
    const [advanced, setAdvanced] = useState<AdvancedState>(EMPTY_ADVANCED)
    const [planCheck, setPlanCheck] = useState<PlanCheck>({ state: 'checking' })

    useEffect(() => {
        let active = true

        nodesApi
            .list()
            .then(({ items }) => {
                if (!active) return
                setNodes(items)
                setNode(items.find((item) => item.agent_up)?.name ?? 'local')
            })
            .catch(() => undefined)
            .finally(() => {
                if (active) setNodesLoaded(true)
            })

        const validate = async (): Promise<void> => {
            if (kind === 'workflow') {
                const detail = await workflowsApi.get(target, 'json')
                const result = await workflowsApi.validate({ definition: detail.definition, format: 'json' })
                let variables: Record<string, unknown>
                try {
                    variables = (JSON.parse(detail.definition) as { variables?: Record<string, unknown> }).variables ?? {}
                } catch {
                    variables = {}
                }
                if (!active) return
                setRows(
                    rowsFor(
                        Object.entries(variables).map(([name, value]) => ({
                            name,
                            type: 'any',
                            required: false,
                            default: value,
                        })),
                    ),
                )
                setCheck({
                    state: 'valid',
                    summary: `Valid · version ${result.workflow.version} · ${result.workflow.step_count} step${
                        result.workflow.step_count === 1 ? '' : 's'
                    }`,
                })
            } else {
                const { items } = await pluginsApi.contracts()
                const contract = items.find((item) => item.qualified_name === target)
                if (!active) return
                if (!contract) {
                    setCheck({ state: 'invalid', error: `Plugin '${target}' is not installed.` })
                    return
                }
                setRows(rowsFor(contract.arguments))
                setCheck({
                    state: 'valid',
                    summary: `Installed · version ${contract.version}${contract.enabled ? '' : ' · disabled'}`,
                })
            }
        }

        validate().catch((cause: unknown) => {
            if (active) setCheck({ state: 'invalid', error: errorMessage(cause, 'Validation failed.') })
        })

        return () => {
            active = false
        }
    }, [kind, target])

    const selected = nodes.find((item) => item.name === node)

    // Why "Start run" is unavailable, shown on hover and under the button row.
    const blocker =
        check.state === 'checking'
            ? 'Validating…'
            : check.state === 'invalid'
              ? check.error
              : !nodesLoaded
                ? 'Loading nodes…'
                : nodes.length === 0
                  ? 'No runner node is available to you.'
                  : !selected?.agent_up
                    ? `Node '${node}' is unavailable; choose another node.`
                    : kind === 'workflow' && planCheck.state === 'invalid'
                      ? planCheck.error
                      : kind === 'workflow' && planCheck.state === 'checking'
                        ? 'Checking the steps to run…'
                        : null

    const start = async () => {
        const parsed = parseRows(rows)
        if (parsed.error) {
            setError(parsed.error)
            return
        }

        setStarting(true)
        setError(null)
        try {
            const { run } =
                kind === 'workflow'
                    ? await runsApi.startWorkflow(
                          target,
                          node,
                          parsed.values,
                          planCheck.state === 'valid' ? runOptionsFor(advanced, planCheck.plan.steps) : {},
                      )
                    : await runsApi.startPlugin(target, node, parsed.values)
            notify.success(`Run #${run.id} started on ${run.node}.`, { title: `${target} started` })
            onClose()
            openRun(run.id)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to start the run.'))
        } finally {
            setStarting(false)
        }
    }

    return (
        <Dialog
            title={kind === 'workflow' ? `Run ${target}?` : `Test ${target}?`}
            subtitle={
                kind === 'workflow'
                    ? 'Runs as you on the selected node. You can follow it live and stop it at any time.'
                    : 'Runs the plugin once, as a single-step workflow, on the selected node.'
            }
            icon={<Play size={18} />}
            onClose={onClose}
            className="start-run-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => {
                            if (!blocker) void start()
                        }}
                        aria-disabled={blocker ? true : undefined}
                        title={blocker ?? undefined}
                        disabled={starting}
                        data-autofocus
                    >
                        {starting ? <LoaderCircle size={15} className="entropy-spin" /> : <Play size={15} />}
                        Start run
                    </button>
                </>
            }
        >
            <div className={`start-run-check is-${check.state}`} role="status">
                {check.state === 'checking' ? (
                    <LoaderCircle size={16} className="entropy-spin" />
                ) : check.state === 'valid' ? (
                    <CheckCircle2 size={16} />
                ) : (
                    <AlertCircle size={16} />
                )}
                <span>
                    {check.state === 'checking'
                        ? 'Validating…'
                        : check.state === 'valid'
                          ? check.summary
                          : check.error}
                </span>
            </div>

            <div className="admin-field">
                <span>Runner node</span>
                <div className="start-run-nodes" role="radiogroup" aria-label="Runner node">
                    {nodes.length === 0 && <p className="run-card-muted">Loading nodes…</p>}
                    {nodes.map((item) => (
                        <label
                            key={item.name}
                            className={`start-run-node${node === item.name ? ' is-selected' : ''}${
                                item.agent_up ? '' : ' is-unavailable'
                            }`}
                        >
                            <input
                                type="radio"
                                name="runner-node"
                                value={item.name}
                                checked={node === item.name}
                                disabled={!item.agent_up}
                                onChange={() => setNode(item.name)}
                            />
                            <Server size={16} aria-hidden="true" />
                            <span>
                                <strong>{item.name}</strong>
                                <small>
                                    {item.host}
                                    {item.metrics
                                        ? ` · CPU ${item.metrics.cpu.percent?.toFixed(0) ?? '—'}% · ${item.running_jobs} running`
                                        : ''}
                                </small>
                            </span>
                            <em>{item.agent_up ? 'Runnable' : 'Unavailable'}</em>
                        </label>
                    ))}
                </div>
            </div>

            <div className="admin-field">
                <span>{kind === 'workflow' ? 'Variables' : 'Arguments'}</span>
                <ParamsEditor
                    rows={rows}
                    onChange={setRows}
                    emptyText={
                        kind === 'workflow'
                            ? 'This workflow declares no variables.'
                            : 'This plugin reads no arguments.'
                    }
                    addLabel={kind === 'workflow' ? 'Add variable' : 'Add argument'}
                />
            </div>

            {kind === 'workflow' && check.state === 'valid' && (
                <RunAdvancedOptions
                    target={target}
                    node={node}
                    nodes={nodes}
                    value={advanced}
                    onChange={setAdvanced}
                    check={planCheck}
                    onCheck={setPlanCheck}
                />
            )}

            {blocker &&
                !error &&
                check.state === 'valid' &&
                nodesLoaded &&
                !(kind === 'workflow' && planCheck.state === 'checking') && (
                <p className="start-run-blocker" role="note">
                    <AlertCircle size={14} aria-hidden="true" />
                    {blocker}
                </p>
            )}

            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}
        </Dialog>
    )
}
