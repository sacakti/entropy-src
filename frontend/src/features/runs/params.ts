import type { PluginArgumentType } from '../../api/plugins.api'

export interface ParamSpec {
    name: string
    type: PluginArgumentType
    required: boolean
    default: unknown
    description?: string
    secret?: boolean
    choices?: unknown[]
    /** For type 'path': a file, a directory or either. */
    path?: 'file' | 'directory' | 'any'
    /** Asked for at run time in interactive runs when left empty. */
    prompt?: boolean
}

export interface ParamRow {
    key: string
    value: string
    spec?: ParamSpec
}

export function display(value: unknown): string {
    if (value === undefined || value === null) return ''
    return typeof value === 'string' ? value : JSON.stringify(value)
}

/** Rows for known parameters first, then any extra values already set. */
export function rowsFor(specs: ParamSpec[], values: Record<string, unknown> = {}): ParamRow[] {
    const rows: ParamRow[] = specs.map((spec) => ({
        key: spec.name,
        value: display(spec.name in values ? values[spec.name] : ''),
        spec,
    }))
    Object.entries(values).forEach(([key, value]) => {
        if (!specs.some((spec) => spec.name === key)) rows.push({ key, value: display(value) })
    })
    return rows
}

/**
 * Parse rows into a parameter object. Blank optional values are left out
 * so the definition's defaults apply.
 */
export function parseRows(
    rows: ParamRow[],
    interactive = false,
): { values: Record<string, unknown>; error: string | null } {
    const values: Record<string, unknown> = {}

    for (const row of rows) {
        const key = row.key.trim()
        const text = row.value.trim()
        if (!key) continue

        if (!text) {
            // Interactive runs ask for "prompt" arguments left empty.
            if (row.spec?.required && row.spec.default === null && !(interactive && row.spec.prompt)) {
                return { values, error: `'${key}' is required.` }
            }
            continue
        }

        const type = row.spec?.type ?? 'any'

        if (type === 'string' || type === 'path') {
            values[key] = row.value
        } else if (type === 'boolean') {
            values[key] = text === 'true'
        } else if (type === 'integer' || type === 'number') {
            const number = Number(text)
            if (Number.isNaN(number) || (type === 'integer' && !Number.isInteger(number))) {
                return { values, error: `'${key}' must be ${type === 'integer' ? 'an integer' : 'a number'}.` }
            }
            values[key] = number
        } else {
            try {
                values[key] = JSON.parse(text)
            } catch {
                if (type === 'list' || type === 'dictionary') {
                    return { values, error: `'${key}' must be valid JSON (${type}).` }
                }
                values[key] = row.value
            }
        }
    }

    return { values, error: null }
}
