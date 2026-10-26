import { Plus, Trash2 } from 'lucide-react'

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
