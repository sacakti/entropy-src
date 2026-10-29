import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, LoaderCircle, Play, Server } from 'lucide-react'

import { pluginsApi } from '../../api/plugins.api'
import { nodesApi, runsApi, type EntropyNode, type Run, type RunMode, type RunRerunConfig } from '../../api/runs.api'
import { workflowsApi } from '../../api/workflows.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from './format'
import { openRun } from './navigation'
import ParamsEditor from './ParamsEditor'
import RunAdvancedOptions from './RunAdvancedOptions'
import { EMPTY_ADVANCED, runOptionsFor, type AdvancedState, type PlanCheck } from './runOptions'
import { parseRows, rowsFor, type ParamRow } from './params'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

type Check = { state: 'checking' } | { state: 'valid'; summary: string } | { state: 'invalid'; error: string }

/**
 * Validate a workflow (or plugin), pick the node to run on, review the
 * inputs and start it; then follow the run live.
 */
export default function StartRunDialog({
    kind,
    target,
    rerunFrom,
    debug: initialDebug = false,
    onStarted,
    onClose,
}: {
    kind: 'workflow' | 'plugin'
    target: string
    rerunFrom?: number
    /** Plugins: start with "Debug run" ticked. */
    debug?: boolean
    /** Called instead of opening the run's live screen. */
    onStarted?: (run: Run) => void
    onClose: () => void
}) {
    const { notify } = useFeedback()
    const [nodes, setNodes] = useState<EntropyNode[]>([])
    const [node, setNode] = useState('local')
    const [rows, setRows] = useState<ParamRow[]>([])
    const [check, setCheck] = useState<Check>({ state: 'checking' })
    const [starting, setStarting] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [nodesLoaded, setNodesLoaded] = useState(false)
    const [advanced, setAdvanced] = useState<AdvancedState>(EMPTY_ADVANCED)
    const [planCheck, setPlanCheck] = useState<PlanCheck>({ state: 'checking' })
    const [rerunConfig, setRerunConfig] = useState<RunRerunConfig | null>(null)
    const [debug, setDebug] = useState(initialDebug)
    const [mode, setMode] = useState<RunMode>('automated')
    // A declared contract refuses arguments it does not list.
    const [declared, setDeclared] = useState(false)

    useEffect(() => {
        let active = true

        nodesApi
            .list()
            .then(({ items }) => {
                if (!active) return
                setNodes(items)
                if (rerunFrom === undefined) {
                    setNode(items.find((item) => item.agent_up)?.name ?? 'local')
                }
            })
            .catch(() => undefined)
            .finally(() => {
                if (active) setNodesLoaded(true)
            })

        const validate = async (): Promise<void> => {
            if (kind === 'workflow') {
                const saved = rerunFrom === undefined ? null : (await runsApi.rerunConfig(rerunFrom)).config
                const definition = saved?.definition ?? (await workflowsApi.get(target, 'json')).definition
                const result = await workflowsApi.validate({ definition, format: 'json' })
                let variables: Record<string, unknown>
                try {
                    variables = (JSON.parse(definition) as { variables?: Record<string, unknown> }).variables ?? {}
                } catch {
                    variables = {}
                }
                if (!active) return
                setRerunConfig(saved)
                if (saved) {
                    setNode(saved.node)
                    const declared = ((JSON.parse(definition) as { steps?: Array<{ name?: string; enabled?: boolean }> }).steps ?? [])
                        .filter((step) => typeof step.name === 'string')
                    const enabled = declared.filter((step) => step.enabled !== false).map((step) => step.name as string)
                    const disabled = declared.filter((step) => step.enabled === false).map((step) => step.name as string)
                    setAdvanced({
                        tags: saved.tags ?? [],
                        excluded: saved.steps === null
                            ? []
                            : enabled.filter((name) => !saved.steps?.includes(name)),
                        // Disabled steps the earlier run chose to run.
                        included: saved.steps === null ? [] : disabled.filter((name) => saved.steps?.includes(name)),
                        stepNodes: saved.step_nodes ?? {},
                    })
                }
                setRows(
                    rowsFor(
                        Object.entries(variables).map(([name, value]) => ({
                            name,
                            type: 'any',
                            required: false,
                            default: value,
                        })),
                        saved?.variables ?? {},
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
                setDeclared(contract.contract === 'declared')
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
    }, [kind, target, rerunFrom])

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
                    : mode === 'interactive' &&
                        (selected?.kind !== 'local' || Object.values(advanced.stepNodes).some((name) => name && name !== node))
                      ? 'Interactive runs run on this server only: choose the local node for every step.'
                    : kind === 'workflow' && planCheck.state === 'invalid'
                      ? planCheck.error
                      : kind === 'workflow' && planCheck.state === 'checking'
                        ? 'Checking the steps to run…'
                        : null

    const start = async () => {
        const parsed = parseRows(rows, mode === 'interactive')
        if (parsed.error) {
            setError(parsed.error)
            return
        }

        setStarting(true)
        setError(null)
        try {
            const { run } =
                kind === 'workflow'
                    ? rerunFrom !== undefined
                        ? await runsApi.rerunWorkflow(rerunFrom, node, parsed.values, {
                              ...(planCheck.state === 'valid' ? runOptionsFor(advanced, planCheck.plan.steps) : {}),
                              mode,
                          })
                        : await runsApi.startWorkflow(target, node, parsed.values, {
                              ...(planCheck.state === 'valid' ? runOptionsFor(advanced, planCheck.plan.steps) : {}),
                              mode,
                          })
                    : await runsApi.startPlugin(target, node, parsed.values, debug, mode)
            notify.success(`Run #${run.id} started on ${run.node}.`, { title: `${target} started` })
            onClose()
            if (onStarted) onStarted(run)
            else openRun(run.id)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to start the run.'))
        } finally {
            setStarting(false)
        }
    }

    return (
        <Dialog
            title={kind === 'workflow' ? `Run ${target}?` : debug ? `Debug ${target}?` : `Test ${target}?`}
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
                    {nodes.length === 0 && <EntropyLoader inline label="Loading nodes…" />}
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
                    allowExtra={kind === 'workflow' || !declared}
                />
            </div>

            <div className="admin-field start-run-mode">
                <span>Mode</span>
                <div className="seg-control" role="radiogroup" aria-label="Run mode">
                    {(
                        [
                            ['automated', 'Automated', 'Runs unattended; a question without a default fails the step.'],
                            ['interactive', 'Interactive', 'Plugins may ask for input (plain or secret) while the run is followed.'],
                        ] as const
                    ).map(([value, label, help]) => (
                        <button
                            key={value}
                            type="button"
                            role="radio"
                            aria-checked={mode === value}
                            className={mode === value ? 'is-active' : ''}
                            title={help}
                            onClick={() => setMode(value)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
                <small>
                    {mode === 'interactive'
                        ? 'Questions appear on the run screen; answer them there. Runs on this server only.'
                        : 'Runs unattended; a question without a default fails the step.'}
                </small>
            </div>

            {kind === 'plugin' && (
                <label className="start-run-debug">
                    <input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} />
                    <span>
                        Debug run
                        <small>Shows the plugin's debug messages and Entropy's debug log (local node).</small>
                    </span>
                </label>
            )}

            {kind === 'workflow' && check.state === 'valid' && (
                <RunAdvancedOptions
                    target={target}
                    node={node}
                    nodes={nodes}
                    value={advanced}
                    onChange={setAdvanced}
                    check={planCheck}
                    onCheck={setPlanCheck}
                    definition={rerunConfig?.definition}
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

        </Dialog>
    )
}
