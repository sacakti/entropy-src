import { useRef } from 'react'
import { KeyRound, Upload } from 'lucide-react'

import type { NodeCredentials, SshAuth } from '../../api/runs.api'

/**
 * SSH credentials for one setup. They are sent once and never stored by
 * Entropy; the node then uses its own revocable token.
 */
export default function CredentialsFields({
    value,
    onChange,
    showForgetHostKey = false,
}: {
    value: NodeCredentials
    onChange: (value: NodeCredentials) => void
    showForgetHostKey?: boolean
}) {
    const fileRef = useRef<HTMLInputElement>(null)
    const set = (patch: Partial<NodeCredentials>) => onChange({ ...value, ...patch })

    return (
        <div className="admin-field admin-field-wide node-credentials">
            <span>Sign in with</span>
            <div className="seg-control" role="radiogroup" aria-label="SSH authentication">
                {(
                    [
                        ['password', 'Password'],
                        ['key', 'Private key'],
                        ['server', "This server's keys"],
                    ] as [SshAuth, string][]
                ).map(([auth, label]) => (
                    <button
                        key={auth}
                        type="button"
                        role="radio"
                        aria-checked={value.auth === auth}
                        className={value.auth === auth ? 'is-active' : ''}
                        onClick={() => set({ auth })}
                    >
                        {label}
                    </button>
                ))}
            </div>

            {value.auth === 'password' && (
                <input
                    type="password"
                    autoComplete="off"
                    value={value.password ?? ''}
                    onChange={(event) => set({ password: event.target.value })}
                    placeholder="SSH password"
                    aria-label="SSH password"
                />
            )}

            {value.auth === 'key' && (
                <>
                    <div className="node-key-box">
                        <textarea
                            rows={4}
                            spellCheck={false}
                            value={value.private_key ?? ''}
                            onChange={(event) => set({ private_key: event.target.value })}
                            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                            aria-label="Private key"
                        />
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => fileRef.current?.click()}
                        >
                            <Upload size={14} /> Load file
                        </button>
                        <input
                            ref={fileRef}
                            type="file"
                            hidden
                            onChange={async (event) => {
                                const file = event.target.files?.[0]
                                if (file && file.size < 32_000) set({ private_key: await file.text() })
                                event.target.value = ''
                            }}
                        />
                    </div>
                    <input
                        type="password"
                        autoComplete="off"
                        value={value.passphrase ?? ''}
                        onChange={(event) => set({ passphrase: event.target.value })}
                        placeholder="Key passphrase (if any)"
                        aria-label="Key passphrase"
                    />
                </>
            )}

            {value.auth === 'server' && (
                <small>Uses the SSH keys of the account running Entropy on the main node.</small>
            )}

            <small className="node-credentials-note">
                <KeyRound size={12} aria-hidden="true" /> Used for this setup only and never stored. The node then
                connects with its own token.
            </small>

            {showForgetHostKey && (
                <label className="schedule-switch">
                    <input
                        type="checkbox"
                        checked={Boolean(value.forget_host_key)}
                        onChange={(event) => set({ forget_host_key: event.target.checked })}
                    />
                    Forget the saved host key (the server was rebuilt)
                </label>
            )}
        </div>
    )
}
