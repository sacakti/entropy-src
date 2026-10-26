import type { PluginArgumentType } from '../../../../api/plugins.api'

/** builder.json: a plugin made from blocks (see lib/plugins/builder.py). */
export interface BuilderModel {
    version?: number
    class_name: string
    inputs: BuilderInput[]
    outputs: BuilderOutput[]
    dependencies: { extensions: Dependency[]; plugins: Dependency[] }
    methods: BuilderMethod[]
}

export interface BuilderInput {
    name: string
    type: PluginArgumentType
    required?: boolean
    default?: unknown
    description?: string
    secret?: boolean
    prompt?: boolean
    choices?: string[]
}

export interface BuilderOutput {
    name: string
    type: PluginArgumentType
    description?: string
}

export interface Dependency {
    name: string
    version?: string
}

export interface BuilderMethod {
    name: string
    description?: string
    blocks: Block[]
}

export type BlockType =
    | 'print'
    | 'set_output'
    | 'set_var'
    | 'if'
    | 'loop'
    | 'switch'
    | 'ask'
    | 'run'
    | 'call'
    | 'fail'

export interface SwitchCase {
    match: string
    body: Block[]
}

export interface Block {
    /** Stable id for the editor; ignored by the generator. */
    id: string
    type: BlockType
    level?: string
    text?: string
    output?: string
    name?: string
    value?: string
    condition?: string
    then?: Block[]
    else?: Block[]
    variable?: string
    over?: string
    body?: Block[]
    cases?: SwitchCase[]
    default?: Block[] | string
    label?: string
    secret?: boolean
    choices?: string[]
    command?: string
    check?: boolean
    method?: string
    message?: string
}

export const LIFECYCLE = ['validate', 'prepare', 'execute', 'cleanup'] as const

export const BLOCKS: Array<{ type: BlockType; label: string; help: string }> = [
    { type: 'print', label: 'Print', help: 'Show a message in the run (self.message.info and friends)' },
    { type: 'set_output', label: 'Set output', help: 'Publish a value as one of the plugin’s outputs' },
    { type: 'set_var', label: 'Set variable', help: 'Compute a value and keep it for later blocks' },
    { type: 'if', label: 'Condition', help: 'Run blocks only when a condition holds (if / else)' },
    { type: 'loop', label: 'Loop', help: 'Repeat blocks for each item of a list (or range(n))' },
    { type: 'switch', label: 'Switch', help: 'Pick blocks by value (switch / case / default)' },
    { type: 'ask', label: 'Ask the user', help: 'Interactive runs: ask for plain or secret input' },
    { type: 'run', label: 'Run a command', help: 'Run a shell command and keep its output' },
    { type: 'call', label: 'Call a method', help: 'Run one of this plugin’s own methods' },
    { type: 'fail', label: 'Fail', help: 'Stop the step with an error message' },
]

let counter = 0
export function newId(): string {
    counter += 1
    return `b${Date.now().toString(36)}${counter}`
}

export function newBlock(type: BlockType, outputs: string[], methods: string[]): Block {
    const id = newId()
    switch (type) {
        case 'print':
            return { id, type, level: 'info', text: 'Hello {name}' }
        case 'set_output':
            return { id, type, output: outputs[0] ?? '', value: "''" }
        case 'set_var':
            return { id, type, name: 'result', value: '0' }
        case 'if':
            return { id, type, condition: 'True', then: [], else: [] }
        case 'loop':
            return { id, type, variable: 'item', over: "['a', 'b']", body: [] }
        case 'switch':
            return { id, type, value: "''", cases: [{ match: "'a'", body: [] }], default: [] }
        case 'ask':
            return { id, type, variable: 'answer', label: 'Your answer', secret: false }
        case 'run':
            return { id, type, variable: 'command', command: 'echo hello', check: true }
        case 'call':
            return { id, type, method: methods.find((name) => !LIFECYCLE.includes(name as never)) ?? '' }
        case 'fail':
            return { id, type, message: 'Something went wrong' }
    }
}

/** Every block gets an id (models written by hand may lack them). */
export function withIds(model: BuilderModel): BuilderModel {
    const fix = (blocks: Block[] | undefined): Block[] =>
        (blocks ?? []).map((block) => ({
            ...block,
            id: block.id || newId(),
            ...(block.then ? { then: fix(block.then) } : {}),
            ...(Array.isArray(block.else) ? { else: fix(block.else) } : {}),
            ...(block.body ? { body: fix(block.body) } : {}),
            ...(Array.isArray(block.default) ? { default: fix(block.default) } : {}),
            ...(block.cases ? { cases: block.cases.map((item) => ({ ...item, body: fix(item.body) })) } : {}),
        }))
    return {
        ...model,
        inputs: model.inputs ?? [],
        outputs: model.outputs ?? [],
        dependencies: { extensions: model.dependencies?.extensions ?? [], plugins: model.dependencies?.plugins ?? [] },
        methods: (model.methods ?? []).map((method) => ({ ...method, blocks: fix(method.blocks) })),
    }
}

/** Where new blocks go: a method's top level or a branch of a block. */
export type Target = { method: number; block?: string; branch?: string }

export const BRANCHES = ['then', 'else', 'body', 'default'] as const

/** Apply `change` to the block list a target names. */
function mapContainer(blocks: Block[], target: Target, change: (list: Block[]) => Block[]): Block[] {
    if (!target.block) return change(blocks)
    return blocks.map((block) => {
        let next = block
        if (block.id === target.block) {
            const branch = target.branch ?? 'body'
            if (branch.startsWith('case:')) {
                const index = Number(branch.slice(5))
                next = {
                    ...block,
                    cases: (block.cases ?? []).map((item, position) =>
                        position === index ? { ...item, body: change(item.body) } : item,
                    ),
                }
            } else {
                const key = branch as (typeof BRANCHES)[number]
                next = { ...block, [key]: change((block[key] as Block[] | undefined) ?? []) }
            }
            return next
        }
        for (const key of BRANCHES) {
            const list = next[key]
            if (Array.isArray(list)) next = { ...next, [key]: mapContainer(list, target, change) }
        }
        if (next.cases) next = { ...next, cases: next.cases.map((item) => ({ ...item, body: mapContainer(item.body, target, change) })) }
        return next
    })
}

export function insertBlock(model: BuilderModel, target: Target, block: Block): BuilderModel {
    return {
        ...model,
        methods: model.methods.map((method, index) =>
            index === target.method ? { ...method, blocks: mapContainer(method.blocks, target, (list) => [...list, block]) } : method,
        ),
    }
}

/** Change, remove or move the block with `id`, wherever it is. */
export function editBlock(
    model: BuilderModel,
    id: string,
    action: { patch?: Partial<Block>; remove?: boolean; move?: -1 | 1 },
): BuilderModel {
    const walk = (blocks: Block[]): Block[] => {
        const index = blocks.findIndex((block) => block.id === id)
        if (index >= 0) {
            const next = [...blocks]
            if (action.remove) next.splice(index, 1)
            else if (action.move) {
                const to = index + action.move
                if (to < 0 || to >= next.length) return blocks
                ;[next[index], next[to]] = [next[to], next[index]]
            } else next[index] = { ...next[index], ...action.patch }
            return next
        }
        return blocks.map((block) => {
            let next = block
            for (const key of BRANCHES) {
                const list = next[key]
                if (Array.isArray(list)) next = { ...next, [key]: walk(list) }
            }
            if (next.cases) next = { ...next, cases: next.cases.map((item) => ({ ...item, body: walk(item.body) })) }
            return next
        })
    }
    return { ...model, methods: model.methods.map((method) => ({ ...method, blocks: walk(method.blocks) })) }
}

/** The model as builder.json stores it (no editor ids). */
export function forSave(model: BuilderModel): BuilderModel {
    const strip = (blocks: Block[] | undefined): Block[] =>
        (blocks ?? []).map((block) => {
            const rest: Partial<Block> = { ...block }
            delete rest.id
            for (const key of BRANCHES) {
                const list = block[key]
                if (Array.isArray(list)) rest[key] = strip(list)
            }
            if (block.cases) rest.cases = block.cases.map((item) => ({ ...item, body: strip(item.body) }))
            return rest as Block
        })
    return { ...model, methods: model.methods.map((method) => ({ ...method, blocks: strip(method.blocks) })) }
}
