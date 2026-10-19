/**
 * Workflow builder model.
 *
 * Converts between workflow definitions (the JSON/YAML documents the server
 * stores) and the editable form state, and validates the form. Keys the form
 * does not edit are carried through untouched so nothing is lost on save.
 */
import { YAMLException, dump, load } from 'js-yaml'

import type { PluginContract } from '../../../api/plugins.api'

export type CodeFormat = 'json' | 'yaml'
export type VariableKind = 'string' | 'number' | 'boolean' | 'list' | 'object' | 'vault'
export type OnFailure = 'abort' | 'continue'
export type WorkspacePosition = 'before' | 'after'
export type WorkspaceType = 'variable' | 'custom'

export interface VariableRow {
    id: string
    name: string
    kind: VariableKind
    /** Text the user edits; parsed according to `kind` on save. */
    text: string
}

export interface StepState {
    id: string
    name: string
    plugin: string
    enabled: boolean
    onFailure: OnFailure
    tags: string[]
    arguments: Record<string, unknown>
    /** Step keys the form does not edit (e.g. suppress_result). */
    extra: Record<string, unknown>
}

export interface WorkspaceState {
    addText: boolean
    position: WorkspacePosition
    type: WorkspaceType
    name: string
}

export interface BuilderState {
    name: string
    version: string
    description: string
    variables: VariableRow[]
    workspace: WorkspaceState
    steps: StepState[]
    extra: Record<string, unknown>
}

export interface Issue {
    severity: 'error' | 'warning'
    message: string
    /** Step id or 'variables' / 'details' / 'workspace' for highlighting. */
    target?: string
}

export interface ParseFailure {
    message: string
    line: number
    column: number
}

const VAULT_REFERENCE = /^\$\{entv:(.+)\}$/
const STEP_REFERENCE = /\$\{steps\.([^.}]+)\.outputs\.([^}]+)\}/g
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/
const TOP_LEVEL_KEYS = ['name', 'version', 'description', 'variables', 'workspace', 'steps']
const STEP_KEYS = ['name', 'plugin', 'enabled', 'on_failure', 'tags', 'arguments']

let sequence = 0

export function newId(prefix: string): string {
    sequence += 1
    return `${prefix}-${Date.now().toString(36)}-${sequence}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function pickExtra(source: Record<string, unknown>, known: string[]): Record<string, unknown> {
    return Object.fromEntries(Object.entries(source).filter(([key]) => !known.includes(key)))
}

// ----------------------------------------------------------------------
// Defaults
// ----------------------------------------------------------------------

export function emptyState(): BuilderState {
    return {
        name: '',
        version: '1.0.0',
        description: '',
        variables: [],
        workspace: { addText: false, position: 'before', type: 'variable', name: '' },
        steps: [],
        extra: {},
    }
}

export function uniqueStepName(base: string, steps: StepState[]): string {
    const names = new Set(steps.map((step) => step.name))
    const root = base.replace(/[^A-Za-z0-9_-]+/g, '_') || 'step'

    if (!names.has(root)) return root

    for (let index = 2; ; index += 1) {
        const candidate = `${root}_${index}`
        if (!names.has(candidate)) return candidate
    }
}

export function newStep(plugin: string, steps: StepState[], contract?: PluginContract): StepState {
    const shortName = plugin.split('.').pop() ?? plugin
    const argumentsWithDefaults: Record<string, unknown> = {}

    // Seed required arguments that have a known default so the step is runnable.
    for (const argument of contract?.arguments ?? []) {
        if (argument.required && argument.default !== null) {
            argumentsWithDefaults[argument.name] = argument.default
        }
    }

    return {
        id: newId('step'),
        name: uniqueStepName(shortName, steps),
        plugin,
        enabled: true,
        onFailure: 'abort',
        tags: [],
        arguments: argumentsWithDefaults,
        extra: {},
    }
}

// ----------------------------------------------------------------------
// Variables
// ----------------------------------------------------------------------

export function variableFromValue(name: string, value: unknown): VariableRow {
    const id = newId('var')

    if (typeof value === 'string') {
        const vault = VAULT_REFERENCE.exec(value)
        return vault
            ? { id, name, kind: 'vault', text: vault[1] }
            : { id, name, kind: 'string', text: value }
    }

    if (typeof value === 'number') return { id, name, kind: 'number', text: String(value) }
    if (typeof value === 'boolean') return { id, name, kind: 'boolean', text: String(value) }
    if (Array.isArray(value)) return { id, name, kind: 'list', text: JSON.stringify(value, null, 2) }
    if (isRecord(value)) return { id, name, kind: 'object', text: JSON.stringify(value, null, 2) }

    return { id, name, kind: 'string', text: value == null ? '' : String(value) }
}

/** Parse a variable row; returns an error message instead of a value when invalid. */
export function variableValue(row: VariableRow): { value: unknown } | { error: string } {
    switch (row.kind) {
        case 'string':
            return { value: row.text }
        case 'number': {
            const number = Number(row.text)
            return row.text.trim() !== '' && Number.isFinite(number)
                ? { value: number }
                : { error: 'must be a number' }
        }
        case 'boolean':
            return { value: row.text === 'true' }
        case 'vault':
            return row.text.includes('/')
                ? { value: `\${entv:${row.text.trim()}}` }
                : { error: "vault reference must be 'namespace/key'" }
        case 'list':
        case 'object': {
            try {
                const parsed: unknown = JSON.parse(row.text || (row.kind === 'list' ? '[]' : '{}'))

                if (row.kind === 'list' ? !Array.isArray(parsed) : !isRecord(parsed)) {
                    return { error: row.kind === 'list' ? 'must be a JSON array' : 'must be a JSON object' }
                }

                return { value: parsed }
            } catch {
                return { error: 'is not valid JSON' }
            }
        }
    }
}

export function convertVariableText(row: VariableRow, kind: VariableKind): string {
    if (kind === row.kind) return row.text

    switch (kind) {
        case 'boolean':
            return row.text === 'true' ? 'true' : 'false'
        case 'list':
            return '[]'
        case 'object':
            return '{}'
        case 'number':
            return Number.isFinite(Number(row.text)) && row.text.trim() !== '' ? row.text : '0'
        default:
            return row.kind === 'list' || row.kind === 'object' ? '' : row.text
    }
}

// ----------------------------------------------------------------------
// Definition <-> state
// ----------------------------------------------------------------------

export function stateFromDefinition(definition: unknown): BuilderState {
    if (!isRecord(definition)) {
        throw new Error('The workflow definition must be an object.')
    }

    const workspace = isRecord(definition.workspace) ? definition.workspace : {}
    const steps = Array.isArray(definition.steps) ? definition.steps : []

    return {
        name: typeof definition.name === 'string' ? definition.name : '',
        version: typeof definition.version === 'string' ? definition.version : '1.0.0',
        description: typeof definition.description === 'string' ? definition.description : '',
        variables: Object.entries(isRecord(definition.variables) ? definition.variables : {}).map(
            ([name, value]) => variableFromValue(name, value),
        ),
        workspace: {
            addText: workspace.add_text === true,
            position: workspace.position === 'after' ? 'after' : 'before',
            type: workspace.type === 'custom' ? 'custom' : 'variable',
            name: typeof workspace.name === 'string' ? workspace.name : '',
        },
        steps: steps.filter(isRecord).map((step) => ({
            id: newId('step'),
            name: typeof step.name === 'string' ? step.name : '',
            plugin: typeof step.plugin === 'string' ? step.plugin : '',
            enabled: step.enabled !== false,
            onFailure: step.on_failure === 'continue' ? 'continue' : 'abort',
            tags: Array.isArray(step.tags) ? step.tags.map(String) : [],
            arguments: isRecord(step.arguments) ? { ...step.arguments } : {},
            extra: pickExtra(step, STEP_KEYS),
        })),
        extra: pickExtra(definition, TOP_LEVEL_KEYS),
    }
}

/** Build the definition object. Invalid variable text is kept as a string. */
export function definitionFromState(state: BuilderState): Record<string, unknown> {
    const variables: Record<string, unknown> = {}

    for (const row of state.variables) {
        if (!row.name.trim()) continue
        const parsed = variableValue(row)
        variables[row.name.trim()] = 'value' in parsed ? parsed.value : row.text
    }

    const definition: Record<string, unknown> = {
        name: state.name.trim(),
        version: state.version.trim(),
        description: state.description,
        variables,
    }

    if (state.workspace.addText) {
        definition.workspace = {
            add_text: true,
            position: state.workspace.position,
            type: state.workspace.type,
            name: state.workspace.name.trim(),
        }
    }

    definition.steps = state.steps.map((step) => ({
        name: step.name.trim(),
        plugin: step.plugin,
        enabled: step.enabled,
        on_failure: step.onFailure,
        tags: step.tags,
        arguments: step.arguments,
        ...step.extra,
    }))

    return { ...definition, ...state.extra }
}

// ----------------------------------------------------------------------
// Text formats
// ----------------------------------------------------------------------

export function serialize(definition: unknown, format: CodeFormat): string {
    return format === 'json'
        ? `${JSON.stringify(definition, null, 4)}\n`
        : dump(definition, { lineWidth: -1, noRefs: true, indent: 2 })
}

function jsonErrorPosition(text: string, error: SyntaxError): { line: number; column: number } {
    const match = /position (\d+)/.exec(error.message)
    const lineMatch = /line (\d+) column (\d+)/.exec(error.message)

    if (lineMatch) return { line: Number(lineMatch[1]), column: Number(lineMatch[2]) }
    if (!match) return { line: 1, column: 1 }

    const before = text.slice(0, Number(match[1]))
    const lines = before.split('\n')
    return { line: lines.length, column: lines[lines.length - 1].length + 1 }
}

export function parse(text: string, format: CodeFormat): { value: unknown } | { failure: ParseFailure } {
    try {
        return { value: format === 'json' ? JSON.parse(text) : load(text) }
    } catch (error) {
        if (error instanceof YAMLException) {
            return {
                failure: {
                    message: error.reason || error.message,
                    line: (error.mark?.line ?? 0) + 1,
                    column: (error.mark?.column ?? 0) + 1,
                },
            }
        }

        const syntax = error as SyntaxError
        return { failure: { message: syntax.message, ...jsonErrorPosition(text, syntax) } }
    }
}

// ----------------------------------------------------------------------
// References
// ----------------------------------------------------------------------

export function stepReferences(value: unknown): Array<{ step: string; key: string }> {
    const found: Array<{ step: string; key: string }> = []

    const visit = (item: unknown) => {
        if (typeof item === 'string') {
            for (const match of item.matchAll(STEP_REFERENCE)) {
                found.push({ step: match[1], key: match[2] })
            }
        } else if (Array.isArray(item)) {
            item.forEach(visit)
        } else if (isRecord(item)) {
            Object.values(item).forEach(visit)
        }
    }

    visit(value)
    return found
}

/** Rewrite ${steps.<old>.outputs...} to the new step name, recursively. */
export function renameStepReferences(value: unknown, from: string, to: string): unknown {
    const pattern = new RegExp(`\\$\\{steps\\.${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.outputs\\.`, 'g')

    if (typeof value === 'string') return value.replace(pattern, `\${steps.${to}.outputs.`)
    if (Array.isArray(value)) return value.map((item) => renameStepReferences(item, from, to))
    if (isRecord(value)) {
        return Object.fromEntries(
            Object.entries(value).map(([key, item]) => [key, renameStepReferences(item, from, to)]),
        )
    }
    return value
}

// ----------------------------------------------------------------------
// Validation
// ----------------------------------------------------------------------

export function validateState(
    state: BuilderState,
    contracts: Map<string, PluginContract>,
): Issue[] {
    const issues: Issue[] = []

    if (!state.name.trim()) issues.push({ severity: 'error', message: 'Workflow name is required.', target: 'details' })
    if (!state.version.trim()) issues.push({ severity: 'error', message: 'Version is required.', target: 'details' })

    const variableNames = new Set<string>()

    for (const row of state.variables) {
        const name = row.name.trim()

        if (!name) {
            issues.push({ severity: 'error', message: 'A variable has no name.', target: 'variables' })
            continue
        }

        if (!IDENTIFIER.test(name)) {
            issues.push({
                severity: 'error',
                message: `Variable '${name}' must start with a letter or _ and use letters, digits or _.`,
                target: 'variables',
            })
        }

        if (variableNames.has(name)) {
            issues.push({ severity: 'error', message: `Variable '${name}' is defined twice.`, target: 'variables' })
        }
        variableNames.add(name)

        const parsed = variableValue(row)
        if ('error' in parsed) {
            issues.push({ severity: 'error', message: `Variable '${name}' ${parsed.error}.`, target: 'variables' })
        }
    }

    if (state.workspace.addText && !state.workspace.name.trim()) {
        issues.push({
            severity: 'error',
            message: 'Workspace name is required when add text is on.',
            target: 'workspace',
        })
    }

    if (
        state.workspace.addText &&
        state.workspace.type === 'variable' &&
        state.workspace.name.trim() &&
        !variableNames.has(state.workspace.name.trim())
    ) {
        issues.push({
            severity: 'warning',
            message: `Workspace variable '${state.workspace.name.trim()}' is not defined.`,
            target: 'workspace',
        })
    }

    if (state.steps.length === 0) {
        issues.push({ severity: 'warning', message: 'The workflow has no steps.', target: 'steps' })
    }

    const earlier = new Set<string>()
    const allSteps = new Set(state.steps.map((step) => step.name.trim()))
    const seen = new Set<string>()

    for (const step of state.steps) {
        const name = step.name.trim()
        const label = name || 'Unnamed step'

        if (!name) issues.push({ severity: 'error', message: 'A step has no name.', target: step.id })
        if (name && seen.has(name)) {
            issues.push({ severity: 'error', message: `Step name '${name}' is used twice.`, target: step.id })
        }
        seen.add(name)

        if (!step.plugin) {
            issues.push({ severity: 'error', message: `${label}: choose a plugin.`, target: step.id })
        }

        const contract = contracts.get(step.plugin)

        if (step.plugin && !contract) {
            issues.push({
                severity: 'warning',
                message: `${label}: plugin '${step.plugin}' is not installed.`,
                target: step.id,
            })
        }

        for (const argument of contract?.arguments ?? []) {
            if (argument.required && (step.arguments[argument.name] === undefined || step.arguments[argument.name] === '')) {
                issues.push({
                    severity: 'error',
                    message: `${label}: argument '${argument.name}' is required.`,
                    target: step.id,
                })
            }
        }

        for (const reference of stepReferences(step.arguments)) {
            if (!allSteps.has(reference.step)) {
                issues.push({
                    severity: 'error',
                    message: `${label}: references unknown step '${reference.step}'.`,
                    target: step.id,
                })
            } else if (!earlier.has(reference.step)) {
                issues.push({
                    severity: 'error',
                    message: `${label}: uses outputs of '${reference.step}', which runs later. Move it above.`,
                    target: step.id,
                })
            } else {
                const producer = state.steps.find((item) => item.name.trim() === reference.step)
                const outputs = contracts.get(producer?.plugin ?? '')?.outputs

                if (outputs && outputs.length > 0 && !outputs.includes(reference.key.split(/[.[]/)[0])) {
                    issues.push({
                        severity: 'warning',
                        message: `${label}: '${reference.step}' is not known to output '${reference.key}'.`,
                        target: step.id,
                    })
                }
            }
        }

        if (name) earlier.add(name)
    }

    return issues
}
