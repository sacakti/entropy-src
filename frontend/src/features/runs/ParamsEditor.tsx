import { useState } from 'react'
import { FolderOpen, KeyRound, Plus, Trash2 } from 'lucide-react'

import ServerFileBrowser from '../../components/files/ServerFileBrowser'
import PickerDialog from '../../components/layout/PickerDialog'
import { loadVaultKeys, vaultReference } from '../vault/vaultKeys'
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
    const [vaultFor, setVaultFor] = useState<number | null>(null)
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
                          ? 'Required (interactive runs ask when left empty)'
                          : spec
                            ? ['list', 'dictionary'].includes(spec.type)
                                ? 'Optional'
                                : 'Optional (interactive runs ask when left empty)'
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
                                type={spec?.secret && !row.value.startsWith('${entv') ? 'password' : 'text'}
                                autoComplete={spec?.secret ? 'new-password' : 'off'}
                                value={row.value}
                                onChange={(event) => update(index, { value: event.target.value })}
                                placeholder={placeholder}
                                title={spec?.description || undefined}
                                inputMode={spec?.type === 'integer' || spec?.type === 'number' ? 'decimal' : undefined}
                                aria-label={spec?.name ?? 'Parameter value'}
                            />
                        )}
                        <span className="params-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                            aria-label={`Use a vault value for ${row.key || 'this value'}`}
                            title="Use a vault value (resolved when the run starts, with your vault access)"
                            onClick={() => setVaultFor(index)}
                        >
                            <KeyRound size={14} />
                        </button>
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
                        </span>
                        {spec?.description && <small className="params-help">{spec.description}</small>}
                    </div>
                )
            })}
            {vaultFor !== null && rows[vaultFor] && (
                <PickerDialog
                    title={`Vault value for ${rows[vaultFor].key || 'this value'}`}
                    subtitle="The run reads it with your vault access when it starts; the value is not stored with the run options. Objects (JSON) arrive as objects."
                    icon={<KeyRound size={18} />}
                    placeholder="Search namespace/key"
                    empty="No vault entries you can read."
                    load={async (query) => {
                        const keys = await loadVaultKeys()
                        const needle = query.trim().toLowerCase()
                        return keys
                            .filter((key) => !needle || key.toLowerCase().includes(needle))
                            .map((key) => ({ id: key, label: key, detail: vaultReference(key) }))
                    }}
                    onPick={(item) => {
                        update(vaultFor, { value: vaultReference(item.id) })
                        setVaultFor(null)
                    }}
                    onClose={() => setVaultFor(null)}
                />
            )}
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
