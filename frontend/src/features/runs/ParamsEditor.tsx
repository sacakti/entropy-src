import { Plus, Trash2 } from 'lucide-react'

import { display, type ParamRow } from './params'

export default function ParamsEditor({
    rows,
    onChange,
    emptyText,
    addLabel = 'Add value',
}: {
    rows: ParamRow[]
    onChange: (rows: ParamRow[]) => void
    emptyText: string
    addLabel?: string
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

                return (
                    <div key={index} className="params-row">
                        {spec ? (
                            <span className="params-key" title={`${spec.type}${spec.required ? ' · required' : ''}`}>
                                {spec.name}
                                <small>{spec.type}</small>
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
                        {spec?.type === 'boolean' ? (
                            <select
                                value={row.value}
                                onChange={(event) => update(index, { value: event.target.value })}
                                aria-label={spec.name}
                            >
                                <option value="">{placeholder}</option>
                                <option value="true">true</option>
                                <option value="false">false</option>
                            </select>
                        ) : (
                            <input
                                value={row.value}
                                onChange={(event) => update(index, { value: event.target.value })}
                                placeholder={placeholder}
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
                    </div>
                )
            })}
            <button
                type="button"
                className="entropy-button entropy-button-ghost entropy-button-sm params-add"
                onClick={() => onChange([...rows, { key: '', value: '' }])}
            >
                <Plus size={14} /> {addLabel}
            </button>
        </div>
    )
}
