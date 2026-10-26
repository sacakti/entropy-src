import { useState } from 'react'
import { FolderOpen, X } from 'lucide-react'

import ServerFileBrowser from '../../../components/files/ServerFileBrowser'
import type { PluginArgumentSpec, PluginArgumentType } from '../../../api/plugins.api'
import { ReferencePicker, type ReferenceGroup } from './controls'

const TYPE_LABELS: Record<PluginArgumentType, string> = {
    string: 'text',
    boolean: 'true / false',
    integer: 'whole number',
    number: 'number',
    path: 'path',
    list: 'list',
    dictionary: 'object',
    any: 'any',
}

function isExpression(value: unknown): value is string {
    return typeof value === 'string' && value.includes('${')
}

function formatDefault(value: unknown): string {
    if (value === null || value === undefined) return ''
    return typeof value === 'string' ? value : JSON.stringify(value)
}

/** JSON text editor that only reports values once they parse. */
function JsonInput({
    value,
    type,
    onChange,
    placeholder,
}: {
    value: unknown
    type: PluginArgumentType
    onChange: (value: unknown) => void
    placeholder: string
}) {
    const valueJson = JSON.stringify(value)
    const [draft, setDraft] = useState(() =>
        value === undefined ? '' : JSON.stringify(value, null, 2),
    )
    const [known, setKnown] = useState<string | undefined>(valueJson)
    const [error, setError] = useState<string | null>(null)

    // Reset the draft only when the value changed from outside this editor.
    if (valueJson !== known) {
        setKnown(valueJson)
        setDraft(value === undefined ? '' : JSON.stringify(value, null, 2))
        setError(null)
    }

    const commit = (text: string) => {
        setDraft(text)

        if (!text.trim()) {
            setError(null)
            setKnown(undefined)
            onChange(undefined)
            return
        }

        try {
            const parsed: unknown = JSON.parse(text)

            if (type === 'list' && !Array.isArray(parsed)) throw new Error('Expected a JSON array.')
            if (
                type === 'dictionary' &&
                (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))
            ) {
                throw new Error('Expected a JSON object.')
            }

            setError(null)
            setKnown(JSON.stringify(parsed))
            onChange(parsed)
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : 'Invalid JSON.')
        }
    }

    return (
        <div className="wf-json-input">
            <textarea
                value={draft}
                onChange={(event) => commit(event.target.value)}
                placeholder={placeholder}
                spellCheck={false}
                rows={Math.min(8, Math.max(2, draft.split('\n').length))}
                aria-invalid={error !== null}
            />
            {error && <small className="wf-field-error">{error}</small>}
        </div>
    )
}

export default function ArgumentField({
    name,
    spec,
    value,
    references,
    onChange,
    onRemove,
}: {
    name: string
    spec?: PluginArgumentSpec
    value: unknown
    references: ReferenceGroup[]
    onChange: (value: unknown) => void
    /** Present for custom arguments the plugin does not declare. */
    onRemove?: () => void
}) {
    const type: PluginArgumentType = spec?.type ?? 'any'
    const set = value !== undefined
    const [browsing, setBrowsing] = useState(false)
    const placeholder =
        spec && spec.default !== null && spec.default !== undefined
            ? `Default: ${formatDefault(spec.default)}`
            : spec?.required
              ? 'Required'
              : 'Not set'

    let editor
    if (isExpression(value)) {
        editor = (
            <input
                className="wf-input wf-expression"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                spellCheck={false}
                aria-label={`${name} expression`}
            />
        )
    } else if (type === 'boolean') {
        editor = (
            <select
                className="entropy-select"
                value={value === undefined ? '' : String(value)}
                onChange={(event) =>
                    onChange(event.target.value === '' ? undefined : event.target.value === 'true')
                }
                aria-label={name}
            >
                <option value="">{placeholder}</option>
                <option value="true">true</option>
                <option value="false">false</option>
            </select>
        )
    } else if (type === 'integer' || type === 'number') {
        editor = (
            <input
                className="wf-input"
                type="number"
                step={type === 'integer' ? 1 : 'any'}
                min={spec?.minimum}
                max={spec?.maximum}
                value={typeof value === 'number' ? value : ''}
                placeholder={placeholder}
                onChange={(event) =>
                    onChange(event.target.value === '' ? undefined : Number(event.target.value))
                }
                aria-label={name}
            />
        )
    } else if (
        type === 'list' ||
        type === 'dictionary' ||
        (value !== undefined && typeof value === 'object')
    ) {
        editor = (
            <JsonInput
                value={value}
                type={type}
                onChange={onChange}
                placeholder={placeholder === 'Not set' ? (type === 'list' ? '[ ]' : '{ }') : placeholder}
            />
        )
    } else {
        editor = (
            <input
                className="wf-input"
                value={value === undefined || value === null ? '' : String(value)}
                placeholder={placeholder}
                onChange={(event) => onChange(event.target.value === '' ? undefined : event.target.value)}
                spellCheck={false}
                aria-label={name}
            />
        )
    }

    return (
        <div className={`wf-argument${set ? ' is-set' : ''}`}>
            <div className="wf-argument-label">
                <code>{name}</code>
                {spec?.required && <span className="wf-required" title="Required">*</span>}
                <span className="wf-argument-type">{spec ? TYPE_LABELS[type] : 'custom'}</span>
            </div>

            <div className="wf-argument-editor">
                {editor}
                {type === 'path' && (
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label={`Browse the server for ${name}`}
                        title="Browse files on the Entropy server"
                        onClick={() => setBrowsing(true)}
                    >
                        <FolderOpen size={14} />
                    </button>
                )}
                <ReferencePicker
                    groups={references}
                    label={`Use a reference for ${name}`}
                    onPick={(expression) => onChange(expression)}
                />
                {(set || onRemove) && (
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label={onRemove ? `Remove argument ${name}` : `Clear ${name}`}
                        title={onRemove ? 'Remove argument' : 'Clear value'}
                        onClick={() => (onRemove ? onRemove() : onChange(undefined))}
                    >
                        <X size={14} />
                    </button>
                )}
            </div>
            {browsing && (
                <ServerFileBrowser
                    kind={spec?.path ?? 'any'}
                    initial={typeof value === 'string' ? value : ''}
                    title={`Choose ${name}`}
                    onPick={(path) => {
                        onChange(path)
                        setBrowsing(false)
                    }}
                    onClose={() => setBrowsing(false)}
                />
            )}
        </div>
    )
}
