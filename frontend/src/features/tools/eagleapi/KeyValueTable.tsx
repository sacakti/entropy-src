import { Plus, Trash2 } from 'lucide-react'

import type { EagleRow } from '../../../api/eagleapi.api'
import { emptyRow } from './model'

/** Editable key/value rows with an enable checkbox (params, headers, form body). */
export default function KeyValueTable({
    rows,
    onChange,
    readOnly,
    keyLabel = 'Key',
    valueLabel = 'Value',
    suggestions,
}: {
    rows: EagleRow[]
    onChange: (rows: EagleRow[]) => void
    readOnly: boolean
    keyLabel?: string
    valueLabel?: string
    /** id of a <datalist> offering vault references for values. */
    suggestions?: string
}) {
    const update = (index: number, patch: Partial<EagleRow>) =>
        onChange(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)))

    return (
        <div className="eagle-kv">
            {rows.length > 0 && (
                <div className="eagle-kv-head" aria-hidden="true">
                    <span />
                    <span>{keyLabel}</span>
                    <span>{valueLabel}</span>
                    <span />
                </div>
            )}
            {rows.map((row, index) => (
                <div className="eagle-kv-row" key={index}>
                    <input
                        type="checkbox"
                        checked={row.enabled}
                        disabled={readOnly}
                        aria-label={`Use ${row.key || 'this row'}`}
                        onChange={(event) => update(index, { enabled: event.target.checked })}
                    />
                    <input
                        type="text"
                        value={row.key}
                        placeholder={keyLabel}
                        aria-label={keyLabel}
                        readOnly={readOnly}
                        spellCheck={false}
                        onChange={(event) => update(index, { key: event.target.value })}
                    />
                    <input
                        type="text"
                        value={row.value}
                        placeholder={valueLabel}
                        aria-label={`${valueLabel} of ${row.key || 'row'}`}
                        readOnly={readOnly}
                        spellCheck={false}
                        list={suggestions}
                        onChange={(event) => update(index, { value: event.target.value })}
                    />
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label={`Remove ${row.key || 'row'}`}
                        disabled={readOnly}
                        onClick={() => onChange(rows.filter((_, position) => position !== index))}
                    >
                        <Trash2 size={14} />
                    </button>
                </div>
            ))}
            {!readOnly && (
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-sm eagle-kv-add"
                    onClick={() => onChange([...rows, emptyRow()])}
                >
                    <Plus size={14} /> Add {keyLabel.toLowerCase()}
                </button>
            )}
            {readOnly && rows.length === 0 && <p className="eagle-muted">None.</p>}
        </div>
    )
}
