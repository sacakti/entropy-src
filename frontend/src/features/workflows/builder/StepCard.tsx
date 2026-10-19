import { useState, type DragEvent } from 'react'
import {
    AlertCircle,
    ArrowDown,
    ArrowUp,
    ChevronDown,
    GripVertical,
    Plus,
    TriangleAlert,
    X,
} from 'lucide-react'

import type { PluginContract } from '../../../api/plugins.api'
import ArgumentField from './ArgumentField'
import { Switch, TagEditor, type ReferenceGroup } from './controls'
import type { Issue, OnFailure, StepState } from './model'

const ARGUMENT_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/

export interface StepDragProps {
    dragging: boolean
    dropPosition: 'before' | 'after' | null
    onDragStart: (event: DragEvent) => void
    onDragEnd: () => void
    onDragOver: (event: DragEvent<HTMLElement>) => void
    onDrop: (event: DragEvent) => void
}

export default function StepCard({
    step,
    index,
    count,
    contract,
    plugins,
    references,
    issues,
    drag,
    onChange,
    onRename,
    onRemove,
    onMove,
}: {
    step: StepState
    index: number
    count: number
    contract?: PluginContract
    plugins: PluginContract[]
    references: ReferenceGroup[]
    issues: Issue[]
    drag: StepDragProps
    onChange: (step: StepState) => void
    onRename: (name: string) => void
    onRemove: () => void
    onMove: (offset: number) => void
}) {
    const [collapsed, setCollapsed] = useState(false)
    const [customName, setCustomName] = useState('')

    const declared = new Set(contract?.arguments.map((argument) => argument.name))
    const custom = Object.keys(step.arguments).filter((name) => !declared.has(name))
    const errors = issues.filter((issue) => issue.severity === 'error')
    const warnings = issues.filter((issue) => issue.severity === 'warning')

    const setArgument = (name: string, value: unknown) => {
        const next = { ...step.arguments }

        if (value === undefined) delete next[name]
        else next[name] = value

        onChange({ ...step, arguments: next })
    }

    const addCustom = () => {
        const name = customName.trim()

        if (!ARGUMENT_NAME.test(name) || name in step.arguments) return

        setArgument(name, '')
        setCustomName('')
    }

    return (
        <article
            className={[
                'wf-step',
                step.enabled ? '' : 'is-disabled',
                drag.dragging ? 'is-dragging' : '',
                drag.dropPosition ? `drop-${drag.dropPosition}` : '',
                errors.length ? 'has-errors' : '',
            ]
                .filter(Boolean)
                .join(' ')}
            onDragOver={drag.onDragOver}
            onDrop={drag.onDrop}
            aria-label={`Step ${index + 1}: ${step.name || 'unnamed'}`}
        >
            <header className="wf-step-header">
                <span
                    className="wf-step-handle"
                    draggable
                    onDragStart={drag.onDragStart}
                    onDragEnd={drag.onDragEnd}
                    title="Drag to reorder"
                    aria-hidden="true"
                >
                    <GripVertical size={16} />
                </span>

                <Switch
                    checked={step.enabled}
                    onChange={(enabled) => onChange({ ...step, enabled })}
                    label={step.enabled ? 'Step enabled' : 'Step disabled'}
                />

                <span className="wf-step-number">{index + 1}</span>
                {!step.enabled && <span className="wf-chip">Disabled</span>}

                <input
                    className="wf-input wf-step-name"
                    value={step.name}
                    onChange={(event) => onRename(event.target.value)}
                    placeholder="Step name"
                    aria-label="Step name"
                    spellCheck={false}
                />

                <div className="wf-step-actions">
                    <TagEditor tags={step.tags} onChange={(tags) => onChange({ ...step, tags })} />

                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label="Move step up"
                        title="Move up"
                        disabled={index === 0}
                        onClick={() => onMove(-1)}
                    >
                        <ArrowUp size={14} />
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label="Move step down"
                        title="Move down"
                        disabled={index === count - 1}
                        onClick={() => onMove(1)}
                    >
                        <ArrowDown size={14} />
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label={collapsed ? 'Expand step' : 'Collapse step'}
                        aria-expanded={!collapsed}
                        onClick={() => setCollapsed((value) => !value)}
                    >
                        <ChevronDown size={15} className={collapsed ? 'wf-rotate' : ''} />
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                        aria-label={`Remove step ${step.name}`}
                        title="Remove step"
                        onClick={onRemove}
                    >
                        <X size={15} />
                    </button>
                </div>
            </header>

            <div className="wf-step-meta">
                <label>
                    <span>Plugin</span>
                    <select
                        className="entropy-select"
                        value={step.plugin}
                        onChange={(event) => onChange({ ...step, plugin: event.target.value })}
                    >
                        {!plugins.some((plugin) => plugin.qualified_name === step.plugin) && (
                            <option value={step.plugin}>{step.plugin || 'Choose a plugin'}</option>
                        )}
                        {plugins.map((plugin) => (
                            <option key={plugin.qualified_name} value={plugin.qualified_name}>
                                {plugin.qualified_name}
                            </option>
                        ))}
                    </select>
                </label>

                <label>
                    <span>On failure</span>
                    <select
                        className="entropy-select"
                        value={step.onFailure}
                        onChange={(event) =>
                            onChange({ ...step, onFailure: event.target.value as OnFailure })
                        }
                    >
                        <option value="abort">Abort workflow</option>
                        <option value="continue">Continue</option>
                    </select>
                </label>

                {step.tags.length > 0 && (
                    <div className="wf-step-tags" aria-label="Tags">
                        {step.tags.map((tag) => (
                            <span key={tag} className="wf-tag">
                                {tag}
                            </span>
                        ))}
                    </div>
                )}
            </div>

            {(errors.length > 0 || warnings.length > 0) && (
                <ul className="wf-step-issues">
                    {[...errors, ...warnings].map((issue) => (
                        <li key={issue.message} className={`is-${issue.severity}`}>
                            {issue.severity === 'error' ? (
                                <AlertCircle size={13} />
                            ) : (
                                <TriangleAlert size={13} />
                            )}
                            {issue.message.replace(/^[^:]+: /, '')}
                        </li>
                    ))}
                </ul>
            )}

            {!collapsed && (
                <div className="wf-step-body">
                    {contract?.description && <p className="wf-step-description">{contract.description}</p>}

                    {contract && contract.arguments.length === 0 && custom.length === 0 && (
                        <p className="wf-muted">
                            This plugin reads no arguments through the Plugin SDK. Add custom
                            arguments if it expects any.
                        </p>
                    )}

                    <div className="wf-arguments">
                        {contract?.arguments.map((spec) => (
                            <ArgumentField
                                key={spec.name}
                                name={spec.name}
                                spec={spec}
                                value={step.arguments[spec.name]}
                                references={references}
                                onChange={(value) => setArgument(spec.name, value)}
                            />
                        ))}

                        {custom.map((name) => (
                            <ArgumentField
                                key={name}
                                name={name}
                                value={step.arguments[name]}
                                references={references}
                                onChange={(value) => setArgument(name, value ?? '')}
                                onRemove={() => setArgument(name, undefined)}
                            />
                        ))}
                    </div>

                    <form
                        className="wf-add-argument"
                        onSubmit={(event) => {
                            event.preventDefault()
                            addCustom()
                        }}
                    >
                        <input
                            className="wf-input"
                            value={customName}
                            onChange={(event) => setCustomName(event.target.value)}
                            placeholder="custom_argument"
                            aria-label="Custom argument name"
                            spellCheck={false}
                        />
                        <button
                            type="submit"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            disabled={
                                !ARGUMENT_NAME.test(customName.trim()) ||
                                customName.trim() in step.arguments
                            }
                        >
                            <Plus size={13} />
                            Add argument
                        </button>
                    </form>
                </div>
            )}
        </article>
    )
}
