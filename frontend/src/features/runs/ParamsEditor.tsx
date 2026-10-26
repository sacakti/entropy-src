import { useState } from 'react'
import { FolderOpen, Plus, Trash2 } from 'lucide-react'

import ServerFileBrowser from '../../components/files/ServerFileBrowser'
import { display, type ParamRow } from './params'

export default function ParamsEditor({
    rows,
    onChange,
    emptyText,
    addLabel = 'Add value',
    allowExtra = true,
}: {
    rows: ParamRow[]
    onChange: (rows: ParamRow[]) => void
    emptyText: string
    addLabel?: string
    /** False when the plugin declares its arguments: anything else is refused. */
    allowExtra?: boolean
}) {
    const [browsing, setBrowsing] = useState<number | null>(null)
    const update = (index: number, patch: Partial<ParamRow>) =>
        onChange(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)))

    return (
        <div className="params-editor">
            {rows.length === 0 && <p className="run-card-muted">{emptyText}</p>}
            {rows.map((row, index) => {
                const spec = row.spec
                const placeholder =
                    spec && spec.default !== null && spec.default !== undefined
                        ? `Default: ${display(spec.default)}`
                        : spec?.required
                          ? 'Required'
                          : spec
                            ? 'Optional'
                            : 'Value (text or JSON)'
                const choices = spec?.choices?.length
                    ? spec.choices.map(display)
                    : spec?.type === 'boolean'
                      ? ['true', 'false']
                      : null
                const title = spec
                    ? [
                          `${spec.type}${spec.required ? ' · required' : ' · optional'}${spec.secret ? ' · secret' : ''}`,
                          spec.description,
                      ]
                          .filter(Boolean)
                          .join('\n')
                    : undefined

                return (
                    <div key={index} className="params-row">
                        {spec ? (
                            <span className="params-key" title={title}>
                                <span>
                                    {spec.name}
                                    {spec.required && (
                                        <b className="params-required" aria-label="required">
                                            *
                                        </b>
                                    )}
                                </span>
                                <small>
                                    {spec.type}
                                    {spec.secret ? ' · secret' : ''}
                                </small>
                            </span>
                        ) : (
                            <input
                                className="params-key-input"
                                value={row.key}
                                onChange={(event) => update(index, { key: event.target.value })}
                                placeholder="name"
                                aria-label="Parameter name"
                            />
                        )}
                        {spec && choices ? (
                            <select
                                value={row.value}
                                onChange={(event) => update(index, { value: event.target.value })}
                                aria-label={spec.name}
                                title={spec.description || undefined}
                            >
                                <option value="">{placeholder}</option>
                                {choices.map((choice) => (
                                    <option key={choice} value={choice}>
                                        {choice}
                                    </option>
                                ))}
                            </select>
                        ) : (
                            <input
                                type={spec?.secret ? 'password' : 'text'}
                                autoComplete={spec?.secret ? 'new-password' : 'off'}
                                value={row.value}
                                onChange={(event) => update(index, { value: event.target.value })}
                                placeholder={placeholder}
                                title={spec?.description || undefined}
                                inputMode={spec?.type === 'integer' || spec?.type === 'number' ? 'decimal' : undefined}
                                aria-label={spec?.name ?? 'Parameter value'}
                            />
                        )}
                        {spec?.type === 'path' && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label={`Browse the server for ${spec.name}`}
                                title="Browse files on the Entropy server"
                                onClick={() => setBrowsing(index)}
                            >
                                <FolderOpen size={14} />
                            </button>
                        )}
                        {!spec && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="Remove value"
                                onClick={() => onChange(rows.filter((_, position) => position !== index))}
                            >
                                <Trash2 size={14} />
                            </button>
                        )}
                        {spec?.description && <small className="params-help">{spec.description}</small>}
                    </div>
                )
            })}
            {browsing !== null && rows[browsing]?.spec && (
                <ServerFileBrowser
                    kind={rows[browsing].spec?.path ?? 'any'}
                    initial={rows[browsing].value}
                    title={`Choose ${rows[browsing].spec?.name}`}
                    onPick={(path) => {
                        update(browsing, { value: path })
                        setBrowsing(null)
                    }}
                    onClose={() => setBrowsing(null)}
                />
            )}
            {allowExtra && (
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-sm params-add"
                    onClick={() => onChange([...rows, { key: '', value: '' }])}
                >
                    <Plus size={14} /> {addLabel}
                </button>
            )}
        </div>
    )
}
