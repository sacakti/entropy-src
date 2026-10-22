import type { ReactNode } from 'react'

import type { EagleTls } from '../../../api/eagleapi.api'

export const VALUE_SUGGESTIONS = 'eagle-vault-values'
export const FILE_SUGGESTIONS = 'eagle-vault-files'

function Field({ label, hint, wide, children }: { label: string; hint?: ReactNode; wide?: boolean; children: ReactNode }) {
    return (
        <label className={`eagle-field${wide ? ' eagle-field-wide' : ''}`}>
            <span>{label}</span>
            {children}
            {hint && <small>{hint}</small>}
        </label>
    )
}

/**
 * TLS settings: server verification, CA bundle and client certificate, as
 * vault references. Used by a request's own TLS (Custom) and by the
 * project's TLS profiles.
 */
export default function TlsFields({
    value,
    onChange,
    readOnly,
}: {
    value: EagleTls
    onChange: (value: EagleTls) => void
    readOnly: boolean
}) {
    const set = (changes: Partial<EagleTls>) => onChange({ ...value, ...changes })
    const text = (current: string, update: (next: string) => void, props: { placeholder: string; list: string; label: string }) => (
        <input
            value={current}
            readOnly={readOnly}
            placeholder={props.placeholder}
            aria-label={props.label}
            list={props.list}
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => update(event.target.value)}
        />
    )

    return (
        <>
            <div className="eagle-field-wide">
                <label className="eagle-check">
                    <input type="checkbox" checked={value.verify} disabled={readOnly} onChange={(event) => set({ verify: event.target.checked })} />
                    <span>Verify the server certificate</span>
                </label>
                {!value.verify && <p className="eagle-warn-text">Verification is off: any server certificate is accepted.</p>}
            </div>
            <Field label="CA bundle (vault file)" wide hint="Optional: trust these CA certificates too (PEM).">
                {text(value.ca_bundle, (next) => set({ ca_bundle: next }), {
                    label: 'CA bundle',
                    list: FILE_SUGGESTIONS,
                    placeholder: '${entvfile:…/CA_BUNDLE}',
                })}
            </Field>
            <Field label="Client certificate" wide>
                <select
                    value={value.client_cert}
                    disabled={readOnly}
                    onChange={(event) => set({ client_cert: event.target.value as EagleTls['client_cert'] })}
                >
                    <option value="none">None</option>
                    <option value="pem">PEM certificate + key</option>
                    <option value="pfx">PFX / P12 keystore</option>
                </select>
            </Field>
            {value.client_cert === 'pem' && (
                <>
                    <Field label="Certificate (vault file)">
                        {text(value.cert, (next) => set({ cert: next }), {
                            label: 'Certificate',
                            list: FILE_SUGGESTIONS,
                            placeholder: '${entvfile:…/{{ENV}}_CERT}',
                        })}
                    </Field>
                    <Field label="Private key (vault file)" hint="Leave empty when the certificate file holds the key.">
                        {text(value.key, (next) => set({ key: next }), {
                            label: 'Private key',
                            list: FILE_SUGGESTIONS,
                            placeholder: '${entvfile:…/{{ENV}}_KEY}',
                        })}
                    </Field>
                </>
            )}
            {value.client_cert === 'pfx' && (
                <Field label="Keystore (vault file)" wide>
                    {text(value.pfx, (next) => set({ pfx: next }), {
                        label: 'Keystore',
                        list: FILE_SUGGESTIONS,
                        placeholder: '${entvfile:…/{{ENV}}_PFX}',
                    })}
                </Field>
            )}
            {value.client_cert !== 'none' && (
                <Field label={value.client_cert === 'pfx' ? 'Keystore password' : 'Key password'} wide hint="Optional; a vault reference keeps it secret.">
                    {text(value.password, (next) => set({ password: next }), {
                        label: 'Password',
                        list: VALUE_SUGGESTIONS,
                        placeholder: '${entv:…/{{ENV}}_PFX_PASSWORD}',
                    })}
                </Field>
            )}
        </>
    )
}
