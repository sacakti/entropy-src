import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, ArrowRight, ChevronRight, CheckCircle2, LoaderCircle, Tag } from 'lucide-react'

import { runsApi, type EntropyNode, type PlannedStep, type RunOptions } from '../../api/runs.api'
import { errorMessage } from './format'
import { runOptionsFor, segmentsLabel, type AdvancedState, type PlanCheck } from './runOptions'

function willRun(step: PlannedStep, state: AdvancedState): boolean {
    if (!step.enabled || state.excluded.includes(step.name)) return false
    return state.tags.length === 0 || (step.tags ?? []).some((tag) => state.tags.includes(tag))
}

/**
 * Collapsed "Advanced" part of the run dialog: filter steps by tag, pick
 * steps, and send steps to other nodes. Steps still run in workflow order;
 * the server checks that every selected step's inputs will exist.
 */
export default function RunAdvancedOptions({
    target,
    node,
    nodes,
    value,
    onChange,
    check,
    onCheck,
    definition,
}: {
    target: string
    node: string
    nodes: EntropyNode[]
    value: AdvancedState
    onChange: (next: AdvancedState) => void
    check: PlanCheck
    onCheck: (next: PlanCheck) => void
    definition?: string
}) {
    const [steps, setSteps] = useState<PlannedStep[]>([])
    const [open, setOpen] = useState(false)

    const options = useMemo(() => runOptionsFor(value, steps), [value, steps])
    const optionsKey = JSON.stringify(options)
    // A rerun with a saved step subset needs the full step list first so the
    // excluded names can be translated back into an explicit selected list.
    const loadingStepsForSelection = steps.length === 0 && value.excluded.length > 0

    // Ask the server for the plan whenever the choices change.
    useEffect(() => {
        let active = true
        const timer = window.setTimeout(() => {
            runsApi
                .planWorkflow(
                    target,
                    node,
                    loadingStepsForSelection ? {} : (JSON.parse(optionsKey) as RunOptions),
                    definition,
                )
                .then((result) => {
                    if (!active) return
                    if (result.valid) {
                        setSteps((current) => (current.length ? current : result.plan.steps))
                        onCheck({ state: 'valid', plan: result.plan })
                    } else {
                        onCheck({ state: 'invalid', error: result.error })
                    }
                })
                .catch((cause: unknown) => {
                    if (active) onCheck({ state: 'invalid', error: errorMessage(cause, 'Unable to plan the run.') })
                })
        }, 250)
        return () => {
            active = false
            window.clearTimeout(timer)
        }
    }, [target, node, optionsKey, onCheck, definition, loadingStepsForSelection])

    const tags = useMemo(
        () => Array.from(new Set(steps.flatMap((step) => step.tags ?? []))).sort(),
        [steps],
    )
    const runnable = nodes.filter((item) => item.agent_up)
    const changed = Boolean(options.tags || options.steps || options.step_nodes)

    const toggleTag = (tag: string) =>
        onChange({
            ...value,
            tags: value.tags.includes(tag) ? value.tags.filter((item) => item !== tag) : [...value.tags, tag],
        })

    const toggleStep = (name: string) =>
        onChange({
            ...value,
            excluded: value.excluded.includes(name)
                ? value.excluded.filter((item) => item !== name)
                : [...value.excluded, name],
        })

    const setStepNode = (name: string, stepNode: string) =>
        onChange({ ...value, stepNodes: { ...value.stepNodes, [name]: stepNode } })

    const summary =
        check.state === 'valid'
            ? `${check.plan.selected.length} of ${check.plan.steps.length} steps · ${segmentsLabel(check.plan)}`
            : check.state === 'invalid'
              ? 'Needs attention'
              : 'Checking…'

    return (
        <section className={`run-advanced${open ? ' is-open' : ''}`}>
            <button
                type="button"
                className="run-advanced-toggle"
                aria-expanded={open}
                onClick={() => setOpen((current) => !current)}
            >
                <ChevronRight size={15} aria-hidden="true" />
                <strong>Advanced</strong>
                <span>Steps, tags and nodes</span>
                <em className={check.state === 'invalid' ? 'is-invalid' : changed ? 'is-changed' : ''}>{summary}</em>
            </button>

            {open && (
                <div className="run-advanced-body">
                    {tags.length > 0 && (
                        <div className="run-advanced-tags" role="group" aria-label="Filter steps by tag">
                            <span>
                                <Tag size={13} aria-hidden="true" /> Only steps tagged
                            </span>
                            {tags.map((tag) => (
                                <button
                                    key={tag}
                                    type="button"
                                    className={`run-tag${value.tags.includes(tag) ? ' is-active' : ''}`}
                                    aria-pressed={value.tags.includes(tag)}
                                    onClick={() => toggleTag(tag)}
                                >
                                    {tag}
                                </button>
                            ))}
                            {value.tags.length > 0 && (
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-sm"
                                    onClick={() => onChange({ ...value, tags: [] })}
                                >
                                    Clear
                                </button>
                            )}
                        </div>
                    )}

                    <ol className="run-advanced-steps">
                        {steps.map((step, index) => {
                            const runs = willRun(step, value)
                            const filtered = step.enabled && value.tags.length > 0 && !(step.tags ?? []).some((tag) => value.tags.includes(tag))
                            const note = !step.enabled
                                ? 'Disabled in the workflow'
                                : filtered
                                  ? 'Filtered out by tag'
                                  : null
                            return (
                                <li key={step.name} className={runs ? '' : 'is-off'}>
                                    <label className="run-advanced-step">
                                        <input
                                            type="checkbox"
                                            checked={runs}
                                            disabled={!step.enabled || filtered}
                                            onChange={() => toggleStep(step.name)}
                                        />
                                        <span className="run-advanced-index">{index + 1}</span>
                                        <span className="run-advanced-name">
                                            <strong>{step.name}</strong>
                                            <small>
                                                {step.plugin}
                                                {step.depends_on?.length
                                                    ? ` · uses ${Array.from(new Set(step.depends_on.map((item) => item.step))).join(', ')}`
                                                    : ''}
                                                {note ? ` · ${note}` : ''}
                                            </small>
                                            {(step.tags ?? []).length > 0 && (
                                                <span className="run-advanced-step-tags">
                                                    {(step.tags ?? []).map((tag) => (
                                                        <span key={tag} className="run-tag">
                                                            {tag}
                                                        </span>
                                                    ))}
                                                </span>
                                            )}
                                        </span>
                                    </label>
                                    <select
                                        className="entropy-select run-advanced-node"
                                        aria-label={`Node for ${step.name}`}
                                        value={value.stepNodes[step.name] ?? ''}
                                        disabled={!runs}
                                        onChange={(event) => setStepNode(step.name, event.target.value)}
                                    >
                                        <option value="">Default ({node})</option>
                                        {runnable
                                            .filter((item) => item.name !== node)
                                            .map((item) => (
                                                <option key={item.name} value={item.name}>
                                                    {item.name}
                                                </option>
                                            ))}
                                    </select>
                                </li>
                            )
                        })}
                    </ol>

                    <div className={`start-run-check is-${check.state}`} role="status">
                        {check.state === 'checking' ? (
                            <LoaderCircle size={16} className="entropy-spin" />
                        ) : check.state === 'valid' ? (
                            <CheckCircle2 size={16} />
                        ) : (
                            <AlertCircle size={16} />
                        )}
                        {check.state === 'valid' ? (
                            <span className="run-advanced-plan">
                                {check.plan.segments.map((segment, index) => (
                                    <span key={index}>
                                        {index > 0 && <ArrowRight size={13} aria-hidden="true" />}
                                        <strong>{segment.node}</strong>: {segment.steps.join(', ')}
                                    </span>
                                ))}
                            </span>
                        ) : (
                            <span>{check.state === 'invalid' ? check.error : 'Checking the plan…'}</span>
                        )}
                    </div>
                    {check.state === 'valid' && check.plan.segments.length > 1 && (
                        <p className="run-card-muted">
                            Steps run one after another; outputs of earlier steps are handed to the next node.
                        </p>
                    )}
                </div>
            )}
        </section>
    )
}
