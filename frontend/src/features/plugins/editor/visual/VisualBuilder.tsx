import { useEffect, useState, type ReactNode } from 'react'
import {
    AlertCircle,
    ArrowDown,
    ArrowUp,
    Boxes,
    Braces,
    CheckCircle2,
    Code2,
    LoaderCircle,
    Plus,
    Trash2,
} from 'lucide-react'

import { extensionsApi } from '../../../../api/extensions.api'
import { pluginsApi, type PluginArgumentType } from '../../../../api/plugins.api'
import {
    BLOCKS,
    LIFECYCLE,
    editBlock,
    insertBlock,
    newBlock,
    type Block,
    type BuilderModel,
    type Dependency,
    type Target,
} from './model'

const TYPES: PluginArgumentType[] = ['string', 'integer', 'number', 'boolean', 'path', 'list', 'dictionary', 'any']
const LEVELS = ['info', 'success', 'warning', 'error', 'debug']
const NAME = /^[A-Za-z_][A-Za-z0-9_]*$/

type Panel = 'logic' | 'inputs' | 'outputs' | 'dependencies' | 'python'

const list = (text: string) =>
    text
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)

/**
 * Build a plugin without code: method boxes made of blocks in the main
 * view; inputs, outputs, logic blocks and dependencies on the right.
 * Entropy writes the Python (shown under "Python").
 */
export default function VisualBuilder({
    model,
    onChange,
    problems,
    source,
    generating,
    readOnly,
}: {
    model: BuilderModel
    onChange: (model: BuilderModel) => void
    problems: string[]
    /** plugin.py as generated from the model. */
    source: string
    generating: boolean
    readOnly: boolean
}) {
    const [panel, setPanel] = useState<Panel>('logic')
    const [target, setTarget] = useState<Target>({ method: Math.max(0, model.methods.findIndex((m) => m.name === 'execute')) })
    const outputs = model.outputs.map((item) => item.name)
    const methods = model.methods.map((item) => item.name)

    const set = (patch: Partial<BuilderModel>) => onChange({ ...model, ...patch })
    const add = (type: Block['type']) => {
        const method = Math.min(target.method, model.methods.length - 1)
        onChange(insertBlock(model, { ...target, method }, newBlock(type, outputs, methods)))
    }
    const edit = (id: string, action: Parameters<typeof editBlock>[2]) => onChange(editBlock(model, id, action))

    const targetLabel = (() => {
        const method = model.methods[target.method]?.name ?? 'execute'
        return target.block ? `${method} › ${target.branch?.startsWith('case:') ? `case ${Number(target.branch.slice(5)) + 1}` : target.branch}` : method
    })()

    return (
        <div className="vb">
            <div className="vb-main" aria-label="Methods">
                <div className="vb-class">
                    <label>
                        <span>Class</span>
                        <input
                            value={model.class_name}
                            disabled={readOnly}
                            onChange={(event) => set({ class_name: event.target.value })}
                            spellCheck={false}
                            aria-invalid={!NAME.test(model.class_name)}
                        />
                    </label>
                    <p>
                        Lifecycle: <code>validate</code> → <code>prepare</code> → <code>execute</code> → <code>cleanup</code>{' '}
                        (always). Expressions are Python over inputs and variables (<code>count &gt; 3</code>,{' '}
                        <code>name.upper()</code>); texts take <code>{'{name}'}</code> placeholders.
                    </p>
                </div>

                {model.methods.map((method, index) => (
                    <section key={index} className={`vb-method${target.method === index && !target.block ? ' is-target' : ''}`}>
                        <header>
                            <Code2 size={15} aria-hidden="true" />
                            {LIFECYCLE.includes(method.name as never) ? (
                                <strong>{method.name}</strong>
                            ) : (
                                <input
                                    className="vb-method-name"
                                    value={method.name}
                                    disabled={readOnly}
                                    aria-label="Method name"
                                    aria-invalid={!NAME.test(method.name)}
                                    onChange={(event) =>
                                        set({
                                            methods: model.methods.map((item, position) =>
                                                position === index ? { ...item, name: event.target.value } : item,
                                            ),
                                        })
                                    }
                                />
                            )}
                            <small>
                                {method.name === 'execute'
                                    ? 'the work; returns the outputs'
                                    : LIFECYCLE.includes(method.name as never)
                                      ? 'lifecycle step'
                                      : 'called by "Call a method"'}
                            </small>
                            {!readOnly && method.name !== 'execute' && (
                                <button
                                    type="button"
                                    className="vb-icon"
                                    aria-label={`Delete method ${method.name}`}
                                    onClick={() => {
                                        set({ methods: model.methods.filter((_, position) => position !== index) })
                                        setTarget({ method: 0 })
                                    }}
                                >
                                    <Trash2 size={14} />
                                </button>
                            )}
                        </header>
                        <BlockList
                            blocks={method.blocks}
                            container={{ method: index }}
                            target={target}
                            onTarget={setTarget}
                            edit={edit}
                            outputs={outputs}
                            methods={methods}
                            readOnly={readOnly}
                        />
                    </section>
                ))}

                {!readOnly && (
                    <div className="vb-add-method">
                        {LIFECYCLE.filter((name) => !methods.includes(name)).map((name) => (
                            <button
                                key={name}
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={() => set({ methods: [...model.methods, { name, blocks: [] }] })}
                            >
                                <Plus size={14} /> {name}
                            </button>
                        ))}
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => {
                                let number = 1
                                while (methods.includes(`step_${number}`)) number += 1
                                set({ methods: [...model.methods, { name: `step_${number}`, blocks: [] }] })
                            }}
                        >
                            <Plus size={14} /> Method
                        </button>
                    </div>
                )}
            </div>

            <aside className="vb-side" aria-label="Builder controls">
                <div className="vb-tabs" role="tablist">
                    {(
                        [
                            ['logic', 'Logic'],
                            ['inputs', `Inputs (${model.inputs.length})`],
                            ['outputs', `Outputs (${model.outputs.length})`],
                            ['dependencies', 'Dependencies'],
                            ['python', 'Python'],
                        ] as const
                    ).map(([id, label]) => (
                        <button
                            key={id}
                            type="button"
                            role="tab"
                            aria-selected={panel === id}
                            className={panel === id ? 'is-active' : ''}
                            onClick={() => setPanel(id)}
                        >
                            {label}
                        </button>
                    ))}
                </div>

                <div className={`vb-status${problems.length ? ' is-error' : ''}`} role="status">
                    {generating ? (
                        <>
                            <LoaderCircle size={14} className="entropy-spin" /> Writing Python…
                        </>
                    ) : problems.length ? (
                        <>
                            <AlertCircle size={14} /> {problems.length} problem{problems.length === 1 ? '' : 's'}
                        </>
                    ) : (
                        <>
                            <CheckCircle2 size={14} /> plugin.py and plugin.json are up to date
                        </>
                    )}
                </div>
                {problems.length > 0 && (
                    <ul className="vb-problems">
                        {problems.map((item, index) => (
                            <li key={index}>{item}</li>
                        ))}
                    </ul>
                )}

                <div className="vb-panel">
                    {panel === 'logic' && (
                        <>
                            <p className="vb-hint">
                                Adds to <strong>{targetLabel}</strong>. Click a method or a branch (then, else, body, case) to
                                choose where.
                            </p>
                            <div className="vb-palette">
                                {BLOCKS.map((item) => (
                                    <button
                                        key={item.type}
                                        type="button"
                                        className="vb-palette-item"
                                        disabled={readOnly || (item.type === 'call' && !methods.some((name) => !LIFECYCLE.includes(name as never)))}
                                        title={item.help}
                                        onClick={() => add(item.type)}
                                    >
                                        <Plus size={13} />
                                        <span>
                                            <strong>{item.label}</strong>
                                            <small>{item.help}</small>
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </>
                    )}

                    {panel === 'inputs' && (
                        <Rows
                            readOnly={readOnly}
                            addLabel="Add input"
                            onAdd={() => {
                                let number = 1
                                while (model.inputs.some((item) => item.name === `input_${number}`)) number += 1
                                set({ inputs: [...model.inputs, { name: `input_${number}`, type: 'string' }] })
                            }}
                        >
                            {model.inputs.map((input, index) => {
                                const update = (patch: Partial<typeof input>) =>
                                    set({ inputs: model.inputs.map((item, position) => (position === index ? { ...item, ...patch } : item)) })
                                return (
                                    <div key={index} className="vb-row">
                                        <div className="vb-row-line">
                                            <input value={input.name} disabled={readOnly} aria-label="Input name" onChange={(event) => update({ name: event.target.value })} />
                                            <select value={input.type} disabled={readOnly} aria-label="Type" onChange={(event) => update({ type: event.target.value as PluginArgumentType })}>
                                                {TYPES.map((type) => (
                                                    <option key={type}>{type}</option>
                                                ))}
                                            </select>
                                            <Remove readOnly={readOnly} label={`Remove ${input.name}`} onClick={() => set({ inputs: model.inputs.filter((_, position) => position !== index) })} />
                                        </div>
                                        <div className="vb-checks">
                                            <label>
                                                <input type="checkbox" disabled={readOnly} checked={Boolean(input.required)} onChange={(event) => update({ required: event.target.checked, ...(event.target.checked ? { default: undefined } : {}) })} />
                                                Mandatory
                                            </label>
                                            <label>
                                                <input type="checkbox" disabled={readOnly} checked={Boolean(input.secret)} onChange={(event) => update({ secret: event.target.checked })} />
                                                Secret
                                            </label>
                                            <label title="Interactive runs ask for it when it is not given">
                                                <input type="checkbox" disabled={readOnly} checked={Boolean(input.prompt)} onChange={(event) => update({ prompt: event.target.checked })} />
                                                Ask at run time
                                            </label>
                                        </div>
                                        {!input.required && (
                                            <input
                                                placeholder="Default (JSON or text)"
                                                disabled={readOnly}
                                                value={input.default === undefined ? '' : typeof input.default === 'string' ? input.default : JSON.stringify(input.default)}
                                                onChange={(event) => {
                                                    const text = event.target.value
                                                    let value: unknown = text === '' ? undefined : text
                                                    if (text && input.type !== 'string' && input.type !== 'path') {
                                                        try {
                                                            value = JSON.parse(text)
                                                        } catch {
                                                            value = text
                                                        }
                                                    }
                                                    update({ default: value })
                                                }}
                                            />
                                        )}
                                        <input placeholder="Choices, comma separated (optional)" disabled={readOnly} value={(input.choices ?? []).join(', ')} onChange={(event) => update({ choices: list(event.target.value).length ? list(event.target.value) : undefined })} />
                                        <input placeholder="Description" disabled={readOnly} value={input.description ?? ''} onChange={(event) => update({ description: event.target.value })} />
                                    </div>
                                )
                            })}
                        </Rows>
                    )}

                    {panel === 'outputs' && (
                        <Rows
                            readOnly={readOnly}
                            addLabel="Add output"
                            onAdd={() => {
                                let number = 1
                                while (model.outputs.some((item) => item.name === `output_${number}`)) number += 1
                                set({ outputs: [...model.outputs, { name: `output_${number}`, type: 'string' }] })
                            }}
                        >
                            {model.outputs.map((output, index) => {
                                const update = (patch: Partial<typeof output>) =>
                                    set({ outputs: model.outputs.map((item, position) => (position === index ? { ...item, ...patch } : item)) })
                                return (
                                    <div key={index} className="vb-row">
                                        <div className="vb-row-line">
                                            <input value={output.name} disabled={readOnly} aria-label="Output name" onChange={(event) => update({ name: event.target.value })} />
                                            <select value={output.type} disabled={readOnly} aria-label="Type" onChange={(event) => update({ type: event.target.value as PluginArgumentType })}>
                                                {TYPES.map((type) => (
                                                    <option key={type}>{type}</option>
                                                ))}
                                            </select>
                                            <Remove readOnly={readOnly} label={`Remove ${output.name}`} onClick={() => set({ outputs: model.outputs.filter((_, position) => position !== index) })} />
                                        </div>
                                        <input placeholder="Description" disabled={readOnly} value={output.description ?? ''} onChange={(event) => update({ description: event.target.value })} />
                                    </div>
                                )
                            })}
                        </Rows>
                    )}

                    {panel === 'dependencies' && (
                        <Dependencies
                            readOnly={readOnly}
                            extensions={model.dependencies.extensions}
                            plugins={model.dependencies.plugins}
                            onChange={(dependencies) => set({ dependencies: { ...model.dependencies, ...dependencies } })}
                        />
                    )}

                    {panel === 'python' && (
                        <pre className="vb-source" aria-label="Generated plugin.py">
                            {source || 'Nothing generated yet.'}
                        </pre>
                    )}
                </div>
            </aside>
        </div>
    )
}

function Rows({ children, readOnly, addLabel, onAdd }: { children: ReactNode; readOnly: boolean; addLabel: string; onAdd: () => void }) {
    return (
        <div className="vb-rows">
            {children}
            {!readOnly && (
                <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={onAdd}>
                    <Plus size={14} /> {addLabel}
                </button>
            )}
        </div>
    )
}

function Remove({ readOnly, label, onClick }: { readOnly: boolean; label: string; onClick: () => void }) {
    if (readOnly) return null
    return (
        <button type="button" className="vb-icon" aria-label={label} title="Remove" onClick={onClick}>
            <Trash2 size={14} />
        </button>
    )
}

function Dependencies({
    extensions,
    plugins,
    readOnly,
    onChange,
}: {
    extensions: Dependency[]
    plugins: Dependency[]
    readOnly: boolean
    onChange: (patch: { extensions?: Dependency[]; plugins?: Dependency[] }) => void
}) {
    const [known, setKnown] = useState<{ extensions: string[]; plugins: string[] }>({ extensions: [], plugins: [] })

    useEffect(() => {
        let active = true
        Promise.all([extensionsApi.list().catch(() => null), pluginsApi.contracts().catch(() => null)]).then(([libraries, installed]) => {
            if (!active) return
            setKnown({
                extensions: [...new Set((libraries?.installed ?? []).map((item) => item.name))].sort(),
                plugins: (installed?.items ?? []).map((item) => item.qualified_name).sort(),
            })
        })
        return () => {
            active = false
        }
    }, [])

    const section = (title: string, help: string, items: Dependency[], key: 'extensions' | 'plugins', options: string[], icon: ReactNode) => (
        <div className="vb-rows">
            <h4>
                {icon} {title}
            </h4>
            <p className="vb-hint">{help}</p>
            <datalist id={`vb-${key}`}>
                {options.map((option) => (
                    <option key={option} value={option} />
                ))}
            </datalist>
            {items.map((item, index) => (
                <div key={index} className="vb-row-line">
                    <input
                        list={`vb-${key}`}
                        value={item.name}
                        disabled={readOnly}
                        placeholder="Name"
                        aria-label={`${title} name`}
                        onChange={(event) => onChange({ [key]: items.map((entry, position) => (position === index ? { ...entry, name: event.target.value } : entry)) })}
                    />
                    <input
                        value={item.version ?? ''}
                        disabled={readOnly}
                        placeholder="Version (optional)"
                        aria-label={`${title} version`}
                        onChange={(event) => onChange({ [key]: items.map((entry, position) => (position === index ? { ...entry, version: event.target.value || undefined } : entry)) })}
                    />
                    <Remove readOnly={readOnly} label={`Remove ${item.name}`} onClick={() => onChange({ [key]: items.filter((_, position) => position !== index) })} />
                </div>
            ))}
            {!readOnly && (
                <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => onChange({ [key]: [...items, { name: '' }] })}>
                    <Plus size={14} /> Add
                </button>
            )}
        </div>
    )

    return (
        <>
            {section('Extensions', 'Python libraries from Extensions (checked when the plugin is installed).', extensions, 'extensions', known.extensions, <Boxes size={14} />)}
            {section('Plugins', 'Other plugins this one needs installed.', plugins, 'plugins', known.plugins, <Braces size={14} />)}
        </>
    )
}

function BlockList({
    blocks,
    container,
    target,
    onTarget,
    edit,
    outputs,
    methods,
    readOnly,
    label,
}: {
    blocks: Block[]
    container: Target
    target: Target
    onTarget: (target: Target) => void
    edit: (id: string, action: Parameters<typeof editBlock>[2]) => void
    outputs: string[]
    methods: string[]
    readOnly: boolean
    label?: string
}) {
    const selected = target.method === container.method && target.block === container.block && target.branch === container.branch
    return (
        <div
            className={`vb-blocks${selected ? ' is-target' : ''}`}
            onClick={(event) => {
                event.stopPropagation()
                onTarget(container)
            }}
        >
            {label && <span className="vb-branch">{label}</span>}
            {blocks.length === 0 && <p className="vb-empty">{readOnly ? 'Nothing here.' : 'Empty: pick a block under Logic to add it here.'}</p>}
            {blocks.map((block, index) => (
                <BlockCard
                    key={block.id}
                    block={block}
                    first={index === 0}
                    last={index === blocks.length - 1}
                    method={container.method}
                    target={target}
                    onTarget={onTarget}
                    edit={edit}
                    outputs={outputs}
                    methods={methods}
                    readOnly={readOnly}
                />
            ))}
        </div>
    )
}

function BlockCard({
    block,
    first,
    last,
    method,
    target,
    onTarget,
    edit,
    outputs,
    methods,
    readOnly,
}: {
    block: Block
    first: boolean
    last: boolean
    method: number
    target: Target
    onTarget: (target: Target) => void
    edit: (id: string, action: Parameters<typeof editBlock>[2]) => void
    outputs: string[]
    methods: string[]
    readOnly: boolean
}) {
    const patch = (value: Partial<Block>) => edit(block.id, { patch: value })
    const info = BLOCKS.find((item) => item.type === block.type)
    const field = (key: keyof Block, placeholder: string, code = true) => (
        <input
            className={code ? 'vb-code' : undefined}
            value={(block[key] as string | undefined) ?? ''}
            placeholder={placeholder}
            disabled={readOnly}
            aria-label={placeholder}
            spellCheck={false}
            onChange={(event) => patch({ [key]: event.target.value })}
        />
    )
    const branch = (name: string, blocks: Block[], text: string) => (
        <BlockList
            blocks={blocks}
            container={{ method, block: block.id, branch: name }}
            target={target}
            onTarget={onTarget}
            edit={edit}
            outputs={outputs}
            methods={methods}
            readOnly={readOnly}
            label={text}
        />
    )

    return (
        <div className={`vb-block is-${block.type}`} onClick={(event) => event.stopPropagation()}>
            <div className="vb-block-head">
                <strong>{info?.label ?? block.type}</strong>
                {!readOnly && (
                    <span className="vb-block-tools">
                        <button type="button" className="vb-icon" disabled={first} aria-label="Move up" onClick={() => edit(block.id, { move: -1 })}>
                            <ArrowUp size={13} />
                        </button>
                        <button type="button" className="vb-icon" disabled={last} aria-label="Move down" onClick={() => edit(block.id, { move: 1 })}>
                            <ArrowDown size={13} />
                        </button>
                        <button type="button" className="vb-icon" aria-label="Delete block" onClick={() => edit(block.id, { remove: true })}>
                            <Trash2 size={13} />
                        </button>
                    </span>
                )}
            </div>

            <div className="vb-block-fields">
                {block.type === 'print' && (
                    <>
                        <select value={block.level ?? 'info'} disabled={readOnly} aria-label="Level" onChange={(event) => patch({ level: event.target.value })}>
                            {LEVELS.map((level) => (
                                <option key={level}>{level}</option>
                            ))}
                        </select>
                        {field('text', 'Text, e.g. Deploying {name}', false)}
                    </>
                )}
                {block.type === 'set_output' && (
                    <>
                        <select value={block.output ?? ''} disabled={readOnly} aria-label="Output" onChange={(event) => patch({ output: event.target.value })}>
                            {!outputs.includes(block.output ?? '') && <option value="">Choose an output…</option>}
                            {outputs.map((name) => (
                                <option key={name}>{name}</option>
                            ))}
                        </select>
                        <span className="vb-eq">=</span>
                        {field('value', 'Expression')}
                    </>
                )}
                {block.type === 'set_var' && (
                    <>
                        {field('name', 'Variable')}
                        <span className="vb-eq">=</span>
                        {field('value', 'Expression')}
                    </>
                )}
                {block.type === 'if' && field('condition', 'Condition, e.g. count > 3')}
                {block.type === 'loop' && (
                    <>
                        <span className="vb-eq">for</span>
                        {field('variable', 'Variable')}
                        <span className="vb-eq">in</span>
                        {field('over', 'List, e.g. hosts or range(3)')}
                    </>
                )}
                {block.type === 'switch' && field('value', 'Value to compare')}
                {block.type === 'ask' && (
                    <>
                        {field('variable', 'Variable')}
                        {field('label', 'Question', false)}
                        <label className="vb-inline-check">
                            <input type="checkbox" disabled={readOnly} checked={Boolean(block.secret)} onChange={(event) => patch({ secret: event.target.checked })} />
                            Secret
                        </label>
                        <input
                            value={(block.choices ?? []).join(', ')}
                            placeholder="Choices (optional, comma separated)"
                            disabled={readOnly}
                            aria-label="Choices"
                            onChange={(event) => patch({ choices: list(event.target.value) })}
                        />
                        <input
                            value={typeof block.default === 'string' ? block.default : ''}
                            placeholder="Default (automated runs use it)"
                            disabled={readOnly}
                            aria-label="Default"
                            onChange={(event) => patch({ default: event.target.value })}
                        />
                    </>
                )}
                {block.type === 'vault' && (
                    <>
                        {field('variable', 'Keep as')}
                        <span className="vb-eq">=</span>
                        {field('key', 'Vault entry: namespace/key')}
                    </>
                )}
                {block.type === 'run' && (
                    <>
                        {field('command', 'Command, e.g. ls {folder}', false)}
                        {field('variable', 'Keep result as')}
                        <label className="vb-inline-check">
                            <input type="checkbox" disabled={readOnly} checked={block.check !== false} onChange={(event) => patch({ check: event.target.checked })} />
                            Fail when it fails
                        </label>
                    </>
                )}
                {block.type === 'call' && (
                    <select value={block.method ?? ''} disabled={readOnly} aria-label="Method" onChange={(event) => patch({ method: event.target.value })}>
                        {!methods.includes(block.method ?? '') && <option value="">Choose a method…</option>}
                        {methods
                            .filter((name) => !LIFECYCLE.includes(name as never))
                            .map((name) => (
                                <option key={name}>{name}</option>
                            ))}
                    </select>
                )}
                {block.type === 'fail' && field('message', 'Message, e.g. {name} is not ready', false)}
            </div>

            {block.type === 'if' && (
                <>
                    {branch('then', block.then ?? [], 'then')}
                    {branch('else', block.else ?? [], 'else')}
                </>
            )}
            {block.type === 'loop' && branch('body', block.body ?? [], 'each time')}
            {block.type === 'switch' && (
                <>
                    {(block.cases ?? []).map((item, index) => (
                        <div key={index} className="vb-case">
                            <div className="vb-case-head">
                                <span className="vb-eq">case</span>
                                <input
                                    className="vb-code"
                                    value={item.match}
                                    disabled={readOnly}
                                    aria-label="Case value"
                                    onChange={(event) =>
                                        patch({
                                            cases: (block.cases ?? []).map((entry, position) =>
                                                position === index ? { ...entry, match: event.target.value } : entry,
                                            ),
                                        })
                                    }
                                />
                                {!readOnly && (
                                    <button
                                        type="button"
                                        className="vb-icon"
                                        aria-label="Remove case"
                                        onClick={() => patch({ cases: (block.cases ?? []).filter((_, position) => position !== index) })}
                                    >
                                        <Trash2 size={13} />
                                    </button>
                                )}
                            </div>
                            {branch(`case:${index}`, item.body, '')}
                        </div>
                    ))}
                    {!readOnly && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => patch({ cases: [...(block.cases ?? []), { match: "''", body: [] }] })}
                        >
                            <Plus size={13} /> Case
                        </button>
                    )}
                    {branch('default', Array.isArray(block.default) ? block.default : [], 'default')}
                </>
            )}
        </div>
    )
}
