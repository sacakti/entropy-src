import { useState } from 'react'
import { Copy, LoaderCircle, Plus, ShieldCheck, Star, Trash2 } from 'lucide-react'

import Dialog from '../../../components/layout/Dialog'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { eagleApi, type EagleSettings, type EagleTlsProfile } from '../../../api/eagleapi.api'
import TlsFields from './TlsFields'

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

function newId(): string {
    return `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function freeName(profiles: EagleTlsProfile[], base: string): string {
    const taken = new Set(profiles.map((profile) => profile.name.toLowerCase()))
    if (!taken.has(base.toLowerCase())) return base
    for (let index = 2; ; index += 1) {
        const name = `${base} ${index}`
        if (!taken.has(name.toLowerCase())) return name
    }
}

const blankProfile = (profiles: EagleTlsProfile[]): EagleTlsProfile => ({
    id: newId(),
    name: freeName(profiles, 'New profile'),
    verify: true,
    client_cert: 'none',
    cert: '',
    key: '',
    pfx: '',
    password: '',
    ca_bundle: '',
})

/**
 * The project's TLS profiles. Requests use the default profile unless they
 * pick another profile or set their own TLS.
 */
export default function TlsSettingsDialog({
    settings,
    readOnlyReason,
    onSaved,
    onClose,
}: {
    settings: EagleSettings
    readOnlyReason: string | null
    onSaved: (settings: EagleSettings) => void
    onClose: () => void
}) {
    const { notify } = useFeedback()
    const readOnly = Boolean(readOnlyReason)
    const [draft, setDraft] = useState<EagleSettings>(settings)
    const [selectedId, setSelectedId] = useState<string | null>(settings.tls_profiles[0]?.id ?? null)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const profiles = draft.tls_profiles
    const selected = profiles.find((profile) => profile.id === selectedId) ?? null
    const changed = JSON.stringify(draft) !== JSON.stringify(settings)

    const update = (id: string, changes: Partial<EagleTlsProfile>) =>
        setDraft((current) => ({
            ...current,
            tls_profiles: current.tls_profiles.map((profile) => (profile.id === id ? { ...profile, ...changes } : profile)),
        }))

    const add = (from?: EagleTlsProfile) => {
        const profile = from
            ? { ...from, id: newId(), name: freeName(profiles, `${from.name} copy`) }
            : blankProfile(profiles)
        setDraft((current) => ({
            ...current,
            tls_profiles: [...current.tls_profiles, profile],
            // The first profile becomes the default.
            default_tls: current.tls_profiles.length ? current.default_tls : profile.id,
        }))
        setSelectedId(profile.id)
    }

    const remove = (id: string) => {
        const rest = profiles.filter((profile) => profile.id !== id)
        setDraft((current) => ({
            tls_profiles: rest,
            default_tls: current.default_tls === id ? '' : current.default_tls,
        }))
        setSelectedId(rest[0]?.id ?? null)
    }

    const save = async () => {
        const names = profiles.map((profile) => profile.name.trim().toLowerCase())
        if (names.some((name) => !name)) {
            setError('Every profile needs a name.')
            return
        }
        if (new Set(names).size !== names.length) {
            setError('Profile names must be different.')
            return
        }
        setSaving(true)
        setError(null)
        try {
            const saved = await eagleApi.saveSettings({
                ...draft,
                tls_profiles: profiles.map((profile) => ({ ...profile, name: profile.name.trim() })),
            })
            notify.success('TLS settings saved.')
            onSaved(saved)
            onClose()
        } catch (cause) {
            setError(errorText(cause, 'The TLS settings were not saved.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title="TLS settings"
            subtitle="Profiles for this project's requests. A request uses the default profile unless it picks another one or sets its own TLS."
            icon={<ShieldCheck size={18} />}
            onClose={onClose}
            className="eagle-tls-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        {readOnly ? 'Close' : 'Cancel'}
                    </button>
                    {!readOnly && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            disabled={!changed || saving}
                            onClick={save}
                        >
                            {saving && <LoaderCircle size={14} className="entropy-spin" />} Save
                        </button>
                    )}
                </>
            }
        >
            {readOnlyReason && <p className="eagle-muted">{readOnlyReason}</p>}
            <div className="eagle-tls-settings">
                <div className="eagle-tls-list">
                    <label className="eagle-field">
                        <span>Project default</span>
                        <select
                            value={draft.default_tls}
                            disabled={readOnly}
                            onChange={(event) => setDraft((current) => ({ ...current, default_tls: event.target.value }))}
                        >
                            <option value="">None (verify, no client certificate)</option>
                            {profiles.map((profile) => (
                                <option key={profile.id} value={profile.id}>
                                    {profile.name || '(unnamed)'}
                                </option>
                            ))}
                        </select>
                    </label>
                    <ul role="listbox" aria-label="TLS profiles">
                        {profiles.map((profile) => (
                            <li key={profile.id}>
                                <button
                                    type="button"
                                    role="option"
                                    aria-selected={profile.id === selectedId}
                                    className={profile.id === selectedId ? 'is-selected' : undefined}
                                    onClick={() => setSelectedId(profile.id)}
                                >
                                    <span>{profile.name || '(unnamed)'}</span>
                                    {profile.id === draft.default_tls && <Star size={13} aria-label="default" />}
                                    {!profile.verify && <span className="eagle-tls-flag">NO VERIFY</span>}
                                </button>
                            </li>
                        ))}
                        {!profiles.length && <li className="eagle-muted">No profiles yet.</li>}
                    </ul>
                    {!readOnly && (
                        <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => add()}>
                            <Plus size={14} /> Add profile
                        </button>
                    )}
                </div>

                <div className="eagle-tls-editor">
                    {selected ? (
                        <div className="eagle-form">
                            <label className="eagle-field eagle-field-wide">
                                <span>Name</span>
                                <input
                                    value={selected.name}
                                    readOnly={readOnly}
                                    maxLength={80}
                                    onChange={(event) => update(selected.id, { name: event.target.value })}
                                />
                            </label>
                            <TlsFields value={selected} readOnly={readOnly} onChange={(value) => update(selected.id, value)} />
                            {!readOnly && (
                                <div className="eagle-field-wide eagle-inline-actions">
                                    {selected.id !== draft.default_tls && (
                                        <button
                                            type="button"
                                            className="entropy-button entropy-button-secondary entropy-button-sm"
                                            onClick={() => setDraft((current) => ({ ...current, default_tls: selected.id }))}
                                        >
                                            <Star size={14} /> Make default
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-sm"
                                        onClick={() => add(selected)}
                                    >
                                        <Copy size={14} /> Duplicate
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-danger entropy-button-sm"
                                        onClick={() => remove(selected.id)}
                                    >
                                        <Trash2 size={14} /> Remove
                                    </button>
                                </div>
                            )}
                        </div>
                    ) : (
                        <p className="eagle-muted">
                            Add a profile with the CA bundle and client certificate your APIs need, and make it the
                            default: every request then uses it.
                        </p>
                    )}
                </div>
            </div>
            {error && (
                <p className="eagle-warn-text" role="alert">
                    {error}
                </p>
            )}
        </Dialog>
    )
}
