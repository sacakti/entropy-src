import { useMemo, useState, type DragEvent } from 'react'
import { Plus, Search, X } from 'lucide-react'

import type { PluginContract } from '../../../api/plugins.api'
import { Switch, type ReferenceGroup } from './controls'
import {
    convertVariableText,
    newId,
    newStep,
    renameStepReferences,
    type BuilderState,
    type Issue,
    type StepState,
    type VariableKind,
    type VariableRow,
    type WorkspacePosition,
    type WorkspaceType,
} from './model'
import StepCard, { type StepDragProps } from './StepCard'

const VARIABLE_KINDS: Array<{ value: VariableKind; label: string }> = [
    { value: 'string', label: 'Text' },
    { value: 'number', label: 'Number' },
    { value: 'boolean', label: 'Boolean' },
    { value: 'list', label: 'List' },
    { value: 'object', label: 'Object' },
    { value: 'vault', label: 'Vault secret' },
]

interface FormViewProps {
    state: BuilderState
    onChange: (state: BuilderState) => void
    contracts: PluginContract[]
    vaultKeys: string[]
    issues: Issue[]
    editing: boolean
}

function Section({
    id,
    title,
    description,
    action,
    children,
    issues,
}: {
    id: string
    title: string
    description: string
    action?: React.ReactNode
    children: React.ReactNode
    issues?: Issue[]
}) {
    return (
        <section className="wf-section" aria-labelledby={`wf-${id}`}>
            <header className="wf-section-heading">
                <div>
                    <h3 id={`wf-${id}`}>{title}</h3>
                    <p>{description}</p>
                </div>
                {action}
            </header>
            {issues && issues.length > 0 && (
                <ul className="wf-section-issues">
                    {issues.map((issue) => (
                        <li key={issue.message} className={`is-${issue.severity}`}>
                            {issue.message}
                        </li>
                    ))}
                </ul>
            )}
            {children}
        </section>
    )
}

function VariableValue({
    row,
    vaultKeys,
    onChange,
}: {
    row: VariableRow
    vaultKeys: string[]
    onChange: (text: string) => void
}) {
    switch (row.kind) {
        case 'boolean':
            return (
                <select
                    className="entropy-select"
                    value={row.text === 'true' ? 'true' : 'false'}
                    onChange={(event) => onChange(event.target.value)}
                    aria-label={`${row.name || 'Variable'} value`}
                >
                    <option value="true">true</option>
                    <option value="false">false</option>
                </select>
            )
        case 'number':
            return (
                <input
                    className="wf-input"
                    type="number"
                    step="any"
                    value={row.text}
                    onChange={(event) => onChange(event.target.value)}
                    aria-label={`${row.name || 'Variable'} value`}
                />
            )
        case 'list':
        case 'object':
            return (
                <textarea
                    className="wf-input wf-code-input"
                    value={row.text}
                    onChange={(event) => onChange(event.target.value)}
                    placeholder={row.kind === 'list' ? '["a", "b"]' : '{"key": "value"}'}
                    rows={Math.min(8, Math.max(2, row.text.split('\n').length))}
                    spellCheck={false}
                    aria-label={`${row.name || 'Variable'} value`}
                />
            )
        case 'vault':
            return (
                <>
                    <input
                        className="wf-input"
                        list={`vault-keys-${row.id}`}
                        value={row.text}
                        onChange={(event) => onChange(event.target.value)}
                        placeholder="namespace/key"
                        spellCheck={false}
                        aria-label={`${row.name || 'Variable'} vault key`}
                    />
                    <datalist id={`vault-keys-${row.id}`}>
                        {vaultKeys.map((key) => (
                            <option key={key} value={key} />
                        ))}
                    </datalist>
                </>
            )
        default:
            return (
                <input
                    className="wf-input"
                    value={row.text}
                    onChange={(event) => onChange(event.target.value)}
                    spellCheck={false}
                    aria-label={`${row.name || 'Variable'} value`}
                />
            )
    }
}

function PluginPicker({
    contracts,
    onPick,
}: {
    contracts: PluginContract[]
    onPick: (plugin: PluginContract) => void
}) {
    const [open, setOpen] = useState(false)
    const [query, setQuery] = useState('')

    const filtered = contracts.filter((plugin) =>
        `${plugin.qualified_name} ${plugin.description ?? ''}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
    )

    return (
        <div className="wf-popover-anchor">
            <button
                type="button"
                className="entropy-button entropy-button-primary entropy-button-icon"
                aria-label="Add step"
                title="Add step"
                aria-haspopup="dialog"
                aria-expanded={open}
                onClick={() => setOpen((value) => !value)}
            >
                <Plus size={18} />
            </button>

            {open && (
                <>
                    <div className="wf-popover-scrim" onClick={() => setOpen(false)} />
                    <div className="wf-popover wf-plugin-popover" role="dialog" aria-label="Choose a plugin">
                        <label className="entropy-search wf-popover-search">
                            <Search size={14} aria-hidden="true" />
                            <input
                                autoFocus
                                value={query}
                                onChange={(event) => setQuery(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === 'Escape') setOpen(false)
                                    if (event.key === 'Enter' && filtered[0]) {
                                        onPick(filtered[0])
                                        setOpen(false)
                                    }
                                }}
                                placeholder="Search plugins…"
                                aria-label="Search plugins"
                            />
                        </label>
                        <div className="wf-popover-scroll">
                            {filtered.length === 0 && <p className="wf-reference-empty">No plugins match.</p>}
                            {filtered.map((plugin) => (
                                <button
                                    key={plugin.qualified_name}
                                    type="button"
                                    className="wf-plugin-option"
                                    onClick={() => {
                                        onPick(plugin)
                                        setOpen(false)
                                        setQuery('')
                                    }}
                                    disabled={!plugin.enabled}
                                >
                                    <strong>{plugin.qualified_name}</strong>
                                    <small>
                                        {plugin.description || 'No description'} · {plugin.arguments.length} argument
                                        {plugin.arguments.length === 1 ? '' : 's'}
                                        {plugin.enabled ? '' : ' · disabled'}
                                    </small>
                                </button>
                            ))}
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}

export default function FormView({ state, onChange, contracts, vaultKeys, issues, editing }: FormViewProps) {
    const [dragIndex, setDragIndex] = useState<number | null>(null)
    const [dropTarget, setDropTarget] = useState<{ index: number; position: 'before' | 'after' } | null>(null)

    const contractMap = useMemo(
        () => new Map(contracts.map((contract) => [contract.qualified_name, contract])),
        [contracts],
    )

    const update = (patch: Partial<BuilderState>) => onChange({ ...state, ...patch })

    // -- variables ------------------------------------------------------

    const setVariable = (id: string, patch: Partial<VariableRow>) =>
        update({
            variables: state.variables.map((row) => (row.id === id ? { ...row, ...patch } : row)),
        })

    // -- steps ----------------------------------------------------------

    const setStep = (id: string, next: StepState) =>
        update({ steps: state.steps.map((step) => (step.id === id ? next : step)) })

    const renameStep = (id: string, name: string) => {
        const previous = state.steps.find((step) => step.id === id)?.name.trim()

        update({
            steps: state.steps.map((step) => {
                if (step.id === id) return { ...step, name }
                // Keep references to this step's outputs pointing at it.
                return previous && name.trim()
                    ? {
                          ...step,
                          arguments: renameStepReferences(step.arguments, previous, name.trim()) as Record<
                              string,
                              unknown
                          >,
                      }
                    : step
            }),
        })
    }

    const moveStep = (from: number, to: number) => {
        if (from === to || to < 0 || to >= state.steps.length) return

        const steps = [...state.steps]
        const [moved] = steps.splice(from, 1)
        steps.splice(to, 0, moved)
        update({ steps })
    }

    const dragProps = (index: number): StepDragProps => ({
        dragging: dragIndex === index,
        dropPosition: dropTarget?.index === index && dragIndex !== index ? dropTarget.position : null,
        onDragStart: (event: DragEvent) => {
            event.dataTransfer.effectAllowed = 'move'
            event.dataTransfer.setData('text/plain', String(index))
            setDragIndex(index)
        },
        onDragEnd: () => {
            setDragIndex(null)
            setDropTarget(null)
        },
        onDragOver: (event: DragEvent<HTMLElement>) => {
            if (dragIndex === null) return
            event.preventDefault()
            event.dataTransfer.dropEffect = 'move'

            const rect = event.currentTarget.getBoundingClientRect()
            const position = event.clientY < rect.top + rect.height / 2 ? 'before' : 'after'

            if (dropTarget?.index !== index || dropTarget.position !== position) {
                setDropTarget({ index, position })
            }
        },
        onDrop: (event: DragEvent) => {
            event.preventDefault()

            if (dragIndex !== null && dropTarget) {
                let target = dropTarget.index + (dropTarget.position === 'after' ? 1 : 0)
                if (dragIndex < target) target -= 1
                moveStep(dragIndex, target)
            }

            setDragIndex(null)
            setDropTarget(null)
        },
    })

    // -- references -----------------------------------------------------

    const variableGroup: ReferenceGroup = {
        label: 'Variables',
        empty: 'Define variables above to reference them.',
        items: state.variables
            .filter((row) => row.name.trim())
            .map((row) => ({
                label: row.name.trim(),
                expression: `\${${row.name.trim()}}`,
                hint: VARIABLE_KINDS.find((kind) => kind.value === row.kind)?.label,
            })),
    }

    const vaultGroup: ReferenceGroup = {
        label: 'Vault secrets',
        empty: 'No vault entries you can read.',
        items: vaultKeys.map((key) => ({ label: key, expression: `\${entv:${key}}` })),
    }

    const referencesFor = (index: number): ReferenceGroup[] => [
        variableGroup,
        {
            label: 'Outputs of earlier steps',
            empty: index === 0 ? 'The first step has no earlier steps.' : 'Earlier steps publish no known outputs.',
            items: state.steps.slice(0, index).flatMap((step) =>
                (contractMap.get(step.plugin)?.outputs ?? []).map((output) => ({
                    label: `${step.name} → ${output}`,
                    expression: `\${steps.${step.name.trim()}.outputs.${output}}`,
                    hint: step.plugin,
                })),
            ),
        },
        vaultGroup,
    ]

    const issuesFor = (target: string) => issues.filter((issue) => issue.target === target)
    const variableNames = state.variables.map((row) => row.name.trim()).filter(Boolean)

    return (
        <div className="wf-form">
            <Section
                id="details"
                title="Details"
                description="Identify the workflow."
                issues={issuesFor('details')}
            >
                <div className="wf-grid wf-grid-details">
                    <label className="wf-field">
                        <span>Name</span>
                        <input
                            className="wf-input"
                            value={state.name}
                            onChange={(event) => update({ name: event.target.value })}
                            placeholder="release_pipeline"
                            disabled={editing}
                            title={editing ? 'The name identifies a saved workflow and cannot change.' : undefined}
                            spellCheck={false}
                        />
                    </label>
                    <label className="wf-field">
                        <span>Version</span>
                        <input
                            className="wf-input"
                            value={state.version}
                            onChange={(event) => update({ version: event.target.value })}
                            placeholder="1.0.0"
                            spellCheck={false}
                        />
                    </label>
                    <label className="wf-field wf-field-wide">
                        <span>Description</span>
                        <input
                            className="wf-input"
                            value={state.description}
                            onChange={(event) => update({ description: event.target.value })}
                            placeholder="What does this workflow do?"
                        />
                    </label>
                </div>
            </Section>

            <Section
                id="variables"
                title="Variables"
                description="Values steps can reference as ${name}. Vault secrets resolve at run time."
                issues={issuesFor('variables')}
                action={
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-icon"
                        aria-label="Add variable"
                        title="Add variable"
                        onClick={() =>
                            update({
                                variables: [
                                    ...state.variables,
                                    { id: newId('var'), name: '', kind: 'string', text: '' },
                                ],
                            })
                        }
                    >
                        <Plus size={16} />
                    </button>
                }
            >
                {state.variables.length === 0 ? (
                    <p className="wf-muted">No variables yet. Add one with +.</p>
                ) : (
                    <div className="wf-variables">
                        {state.variables.map((row) => (
                            <div key={row.id} className="wf-variable">
                                <input
                                    className="wf-input"
                                    value={row.name}
                                    onChange={(event) => setVariable(row.id, { name: event.target.value })}
                                    placeholder="name"
                                    aria-label="Variable name"
                                    spellCheck={false}
                                />
                                <select
                                    className="entropy-select"
                                    value={row.kind}
                                    onChange={(event) => {
                                        const kind = event.target.value as VariableKind
                                        setVariable(row.id, { kind, text: convertVariableText(row, kind) })
                                    }}
                                    aria-label="Variable type"
                                >
                                    {VARIABLE_KINDS.map((kind) => (
                                        <option key={kind.value} value={kind.value}>
                                            {kind.label}
                                        </option>
                                    ))}
                                </select>
                                <div className="wf-variable-value">
                                    <VariableValue
                                        row={row}
                                        vaultKeys={vaultKeys}
                                        onChange={(text) => setVariable(row.id, { text })}
                                    />
                                </div>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                    aria-label={`Remove variable ${row.name}`}
                                    title="Remove variable"
                                    onClick={() =>
                                        update({ variables: state.variables.filter((item) => item.id !== row.id) })
                                    }
                                >
                                    <X size={14} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </Section>

            <Section
                id="workspace"
                title="Workspace"
                description="Optionally add text to each run's workspace folder name."
                issues={issuesFor('workspace')}
                action={
                    <Switch
                        checked={state.workspace.addText}
                        onChange={(addText) => update({ workspace: { ...state.workspace, addText } })}
                        label="Add text to workspace name"
                    />
                }
            >
                {state.workspace.addText ? (
                    <div className="wf-grid wf-grid-workspace">
                        <label className="wf-field">
                            <span>Position</span>
                            <select
                                className="entropy-select"
                                value={state.workspace.position}
                                onChange={(event) =>
                                    update({
                                        workspace: {
                                            ...state.workspace,
                                            position: event.target.value as WorkspacePosition,
                                        },
                                    })
                                }
                            >
                                <option value="before">Before the generated name</option>
                                <option value="after">After the generated name</option>
                            </select>
                        </label>
                        <label className="wf-field">
                            <span>Type</span>
                            <select
                                className="entropy-select"
                                value={state.workspace.type}
                                onChange={(event) =>
                                    update({
                                        workspace: {
                                            ...state.workspace,
                                            type: event.target.value as WorkspaceType,
                                        },
                                    })
                                }
                            >
                                <option value="variable">Variable value</option>
                                <option value="custom">Custom text</option>
                            </select>
                        </label>
                        <label className="wf-field">
                            <span>{state.workspace.type === 'variable' ? 'Variable' : 'Text'}</span>
                            {state.workspace.type === 'variable' ? (
                                <select
                                    className="entropy-select"
                                    value={state.workspace.name}
                                    onChange={(event) =>
                                        update({ workspace: { ...state.workspace, name: event.target.value } })
                                    }
                                >
                                    <option value="">Choose a variable</option>
                                    {state.workspace.name && !variableNames.includes(state.workspace.name) && (
                                        <option value={state.workspace.name}>{state.workspace.name}</option>
                                    )}
                                    {variableNames.map((name) => (
                                        <option key={name} value={name}>
                                            {name}
                                        </option>
                                    ))}
                                </select>
                            ) : (
                                <input
                                    className="wf-input"
                                    value={state.workspace.name}
                                    onChange={(event) =>
                                        update({ workspace: { ...state.workspace, name: event.target.value } })
                                    }
                                    placeholder="release"
                                    spellCheck={false}
                                />
                            )}
                        </label>
                    </div>
                ) : (
                    <p className="wf-muted">Off: runs use the generated workspace name.</p>
                )}
            </Section>

            <Section
                id="steps"
                title={`Steps (${state.steps.length})`}
                description="Steps run top to bottom. Drag a card by its handle to reorder."
                issues={issuesFor('steps')}
                action={
                    <PluginPicker
                        contracts={contracts}
                        onPick={(contract) =>
                            update({
                                steps: [
                                    ...state.steps,
                                    newStep(contract.qualified_name, state.steps, contract),
                                ],
                            })
                        }
                    />
                }
            >
                {state.steps.length === 0 ? (
                    <p className="wf-muted">No steps yet. Add a plugin with +.</p>
                ) : (
                    <div className="wf-steps" onDragLeave={(event) => {
                        if (!event.currentTarget.contains(event.relatedTarget as Node)) setDropTarget(null)
                    }}>
                        {state.steps.map((step, index) => (
                            <StepCard
                                key={step.id}
                                step={step}
                                index={index}
                                count={state.steps.length}
                                contract={contractMap.get(step.plugin)}
                                plugins={contracts}
                                references={referencesFor(index)}
                                issues={issuesFor(step.id)}
                                drag={dragProps(index)}
                                onChange={(next) => setStep(step.id, next)}
                                onRename={(name) => renameStep(step.id, name)}
                                onRemove={() => update({ steps: state.steps.filter((item) => item.id !== step.id) })}
                                onMove={(offset) => moveStep(index, index + offset)}
                            />
                        ))}
                    </div>
                )}
            </Section>
        </div>
    )
}
