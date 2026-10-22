import { lazy, Suspense, useState, type ReactNode } from 'react'

import type { EagleRequestData } from '../../../api/eagleapi.api'
import KeyValueTable from './KeyValueTable'
import { METHODS } from './model'

const CodeEditor = lazy(() => import('./CodeEditor'))

type Tab = 'params' | 'headers' | 'body' | 'auth' | 'tls' | 'polling' | 'options'

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

function Toggle({
    checked,
    onChange,
    disabled,
    children,
}: {
    checked: boolean
    onChange: (value: boolean) => void
    disabled: boolean
    children: ReactNode
}) {
    return (
        <label className="eagle-check">
            <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
            <span>{children}</span>
        </label>
    )
}

/** The request's tabs: params, headers, body, auth, TLS, polling, options. */
export default function RequestEditor({
    draft,
    onChange,
    readOnly,
}: {
    draft: EagleRequestData
    onChange: (draft: EagleRequestData) => void
    readOnly: boolean
}) {
    const [tab, setTab] = useState<Tab>('params')

    const set = <K extends keyof EagleRequestData>(key: K, value: EagleRequestData[K]) => onChange({ ...draft, [key]: value })
    const body = draft.body
    const auth = draft.auth
    const tls = draft.tls
    const polling = draft.polling
    const enabledCount = (rows: { enabled: boolean; key: string }[]) => rows.filter((row) => row.enabled && row.key.trim()).length

    const tabs: { id: Tab; label: string; badge?: string }[] = [
        { id: 'params', label: 'Params', badge: enabledCount(draft.params) ? String(enabledCount(draft.params)) : undefined },
        { id: 'headers', label: 'Headers', badge: enabledCount(draft.headers) ? String(enabledCount(draft.headers)) : undefined },
        { id: 'body', label: 'Body', badge: body.mode !== 'none' ? body.mode.toUpperCase() : undefined },
        { id: 'auth', label: 'Auth', badge: auth.type !== 'none' ? auth.type.toUpperCase() : undefined },
        { id: 'tls', label: 'TLS', badge: !tls.verify ? 'NO VERIFY' : tls.client_cert !== 'none' ? 'CERT' : undefined },
        { id: 'polling', label: 'Polling', badge: polling.enabled ? 'ON' : undefined },
        { id: 'options', label: 'Options' },
    ]

    const text = (value: string, update: (value: string) => void, props: { placeholder?: string; type?: string; list?: string; label: string }) => (
        <input
            type={props.type ?? 'text'}
            value={value}
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
        <div className="eagle-editor">
            <div className="eagle-tabs" role="tablist" aria-label="Request settings">
                {tabs.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        role="tab"
                        aria-selected={tab === item.id}
                        className={tab === item.id ? 'is-active' : ''}
                        onClick={() => setTab(item.id)}
                    >
                        {item.label}
                        {item.badge && <span className="eagle-tab-badge">{item.badge}</span>}
                    </button>
                ))}
            </div>

            <div className="eagle-tab-panel" role="tabpanel">
                {tab === 'params' && (
                    <KeyValueTable
                        rows={draft.params}
                        onChange={(rows) => set('params', rows)}
                        readOnly={readOnly}
                        keyLabel="Parameter"
                        suggestions={VALUE_SUGGESTIONS}
                    />
                )}

                {tab === 'headers' && (
                    <KeyValueTable
                        rows={draft.headers}
                        onChange={(rows) => set('headers', rows)}
                        readOnly={readOnly}
                        keyLabel="Header"
                        suggestions={VALUE_SUGGESTIONS}
                    />
                )}

                {tab === 'body' && (
                    <div className="eagle-stack">
                        <div className="eagle-segmented" role="radiogroup" aria-label="Body type">
                            {(['none', 'json', 'form', 'raw'] as const).map((mode) => (
                                <button
                                    key={mode}
                                    type="button"
                                    role="radio"
                                    aria-checked={body.mode === mode}
                                    className={body.mode === mode ? 'is-active' : ''}
                                    disabled={readOnly}
                                    onClick={() => set('body', { ...body, mode })}
                                >
                                    {{ none: 'None', json: 'JSON', form: 'Form URL-encoded', raw: 'Raw text' }[mode]}
                                </button>
                            ))}
                        </div>
                        {body.mode === 'none' && <p className="eagle-muted">This request has no body.</p>}
                        {body.mode === 'json' && (
                            <div className="eagle-code eagle-code-input">
                                <Suspense fallback={<pre className="eagle-pre">{body.json}</pre>}>
                                    <CodeEditor
                                        value={body.json}
                                        language="json"
                                        readOnly={readOnly}
                                        label="JSON body"
                                        onChange={(value) => set('body', { ...body, json: value })}
                                    />
                                </Suspense>
                            </div>
                        )}
                        {body.mode === 'form' && (
                            <KeyValueTable
                                rows={body.form}
                                onChange={(rows) => set('body', { ...body, form: rows })}
                                readOnly={readOnly}
                                keyLabel="Field"
                                suggestions={VALUE_SUGGESTIONS}
                            />
                        )}
                        {body.mode === 'raw' && (
                            <>
                                <Field label="Content-Type">
                                    {text(body.content_type, (value) => set('body', { ...body, content_type: value }), {
                                        label: 'Content-Type',
                                        placeholder: 'text/plain',
                                    })}
                                </Field>
                                <div className="eagle-code eagle-code-input">
                                    <Suspense fallback={<pre className="eagle-pre">{body.raw}</pre>}>
                                        <CodeEditor
                                            value={body.raw}
                                            language={body.content_type.includes('xml') ? 'xml' : 'plaintext'}
                                            readOnly={readOnly}
                                            label="Raw body"
                                            onChange={(value) => set('body', { ...body, raw: value })}
                                        />
                                    </Suspense>
                                </div>
                            </>
                        )}
                    </div>
                )}

                {tab === 'auth' && (
                    <div className="eagle-form">
                        <Field label="Type" wide>
                            <select
                                value={auth.type}
                                disabled={readOnly}
                                onChange={(event) => set('auth', { ...auth, type: event.target.value as typeof auth.type })}
                            >
                                <option value="none">No auth</option>
                                <option value="basic">Basic</option>
                                <option value="bearer">Bearer token</option>
                                <option value="oauth2">OAuth2 client credentials</option>
                            </select>
                        </Field>
                        {auth.type === 'basic' && (
                            <>
                                <Field label="Username">
                                    {text(auth.username, (value) => set('auth', { ...auth, username: value }), { label: 'Username', list: VALUE_SUGGESTIONS })}
                                </Field>
                                <Field label="Password">
                                    {text(auth.password, (value) => set('auth', { ...auth, password: value }), {
                                        label: 'Password',
                                        list: VALUE_SUGGESTIONS,
                                        placeholder: '${entv:…/PASSWORD}',
                                    })}
                                </Field>
                            </>
                        )}
                        {auth.type === 'bearer' && (
                            <Field label="Token" wide>
                                {text(auth.token, (value) => set('auth', { ...auth, token: value }), {
                                    label: 'Token',
                                    list: VALUE_SUGGESTIONS,
                                    placeholder: '${entv:…/TOKEN}',
                                })}
                            </Field>
                        )}
                        {auth.type === 'oauth2' && (
                            <>
                                <Field label="Token URL" wide>
                                    {text(auth.token_url, (value) => set('auth', { ...auth, token_url: value }), {
                                        label: 'Token URL',
                                        list: VALUE_SUGGESTIONS,
                                        placeholder: 'https://login.example.com/oauth2/token',
                                    })}
                                </Field>
                                <Field label="Client ID">
                                    {text(auth.client_id, (value) => set('auth', { ...auth, client_id: value }), { label: 'Client ID', list: VALUE_SUGGESTIONS })}
                                </Field>
                                <Field label="Client secret">
                                    {text(auth.client_secret, (value) => set('auth', { ...auth, client_secret: value }), {
                                        label: 'Client secret',
                                        list: VALUE_SUGGESTIONS,
                                    })}
                                </Field>
                                <Field label="Scope">
                                    {text(auth.scope, (value) => set('auth', { ...auth, scope: value }), { label: 'Scope', placeholder: 'optional' })}
                                </Field>
                                <Field label="Send client credentials">
                                    <select
                                        value={auth.client_auth}
                                        disabled={readOnly}
                                        onChange={(event) => set('auth', { ...auth, client_auth: event.target.value as 'body' | 'basic' })}
                                    >
                                        <option value="body">In the request body</option>
                                        <option value="basic">As a Basic auth header</option>
                                    </select>
                                </Field>
                                <p className="eagle-muted eagle-field-wide">
                                    The token is fetched with the request's TLS settings, then sent as a Bearer token.
                                </p>
                            </>
                        )}
                        {auth.type !== 'none' && (
                            <p className="eagle-muted eagle-field-wide">
                                Use vault references (e.g. <code>{'${entv:ns/{{ENV}}_CLIENT_SECRET}'}</code>) rather than typing secrets.
                            </p>
                        )}
                    </div>
                )}

                {tab === 'tls' && (
                    <div className="eagle-form">
                        <div className="eagle-field-wide">
                            <Toggle checked={tls.verify} disabled={readOnly} onChange={(value) => set('tls', { ...tls, verify: value })}>
                                Verify the server certificate
                            </Toggle>
                            {!tls.verify && <p className="eagle-warn-text">Verification is off: any server certificate is accepted.</p>}
                        </div>
                        <Field label="CA bundle (vault file)" wide hint="Optional: trust these CA certificates too (PEM).">
                            {text(tls.ca_bundle, (value) => set('tls', { ...tls, ca_bundle: value }), {
                                label: 'CA bundle',
                                list: FILE_SUGGESTIONS,
                                placeholder: '${entvfile:…/CA_BUNDLE}',
                            })}
                        </Field>
                        <Field label="Client certificate" wide>
                            <select
                                value={tls.client_cert}
                                disabled={readOnly}
                                onChange={(event) => set('tls', { ...tls, client_cert: event.target.value as typeof tls.client_cert })}
                            >
                                <option value="none">None</option>
                                <option value="pem">PEM certificate + key</option>
                                <option value="pfx">PFX / P12 keystore</option>
                            </select>
                        </Field>
                        {tls.client_cert === 'pem' && (
                            <>
                                <Field label="Certificate (vault file)">
                                    {text(tls.cert, (value) => set('tls', { ...tls, cert: value }), {
                                        label: 'Certificate',
                                        list: FILE_SUGGESTIONS,
                                        placeholder: '${entvfile:…/{{ENV}}_CERT}',
                                    })}
                                </Field>
                                <Field label="Private key (vault file)" hint="Leave empty when the certificate file holds the key.">
                                    {text(tls.key, (value) => set('tls', { ...tls, key: value }), {
                                        label: 'Private key',
                                        list: FILE_SUGGESTIONS,
                                        placeholder: '${entvfile:…/{{ENV}}_KEY}',
                                    })}
                                </Field>
                            </>
                        )}
                        {tls.client_cert === 'pfx' && (
                            <Field label="Keystore (vault file)" wide>
                                {text(tls.pfx, (value) => set('tls', { ...tls, pfx: value }), {
                                    label: 'Keystore',
                                    list: FILE_SUGGESTIONS,
                                    placeholder: '${entvfile:…/{{ENV}}_PFX}',
                                })}
                            </Field>
                        )}
                        {tls.client_cert !== 'none' && (
                            <Field label={tls.client_cert === 'pfx' ? 'Keystore password' : 'Key password'} wide hint="Optional.">
                                {text(tls.password, (value) => set('tls', { ...tls, password: value }), {
                                    label: 'Password',
                                    list: VALUE_SUGGESTIONS,
                                    placeholder: '${entv:…/{{ENV}}_PFX_PASSWORD}',
                                })}
                            </Field>
                        )}
                    </div>
                )}

                {tab === 'polling' && (
                    <div className="eagle-form">
                        <div className="eagle-field-wide">
                            <Toggle
                                checked={polling.enabled}
                                disabled={readOnly}
                                onChange={(value) => set('polling', { ...polling, enabled: value })}
                            >
                                Poll after the request
                            </Toggle>
                            <p className="eagle-muted">
                                Read a poll URL from the response, then call it every few seconds until the stop condition.
                            </p>
                        </div>
                        {polling.enabled && (
                            <>
                                <Field label="Find the poll URL in">
                                    <select
                                        value={polling.extract.source}
                                        disabled={readOnly}
                                        onChange={(event) =>
                                            set('polling', {
                                                ...polling,
                                                extract: { ...polling.extract, source: event.target.value as typeof polling.extract.source },
                                            })
                                        }
                                    >
                                        <option value="json">The JSON body (path)</option>
                                        <option value="header">A response header</option>
                                        <option value="regex">The body (regex, 1 group)</option>
                                    </select>
                                </Field>
                                <Field
                                    label={{ json: 'JSON path', header: 'Header name', regex: 'Regular expression' }[polling.extract.source]}
                                    hint={
                                        {
                                            json: 'e.g. data.links.status, $.items[0].href',
                                            header: 'e.g. Location',
                                            regex: 'e.g. "status_url":\\s*"([^"]+)"',
                                        }[polling.extract.source]
                                    }
                                >
                                    {text(
                                        polling.extract.expression,
                                        (value) => set('polling', { ...polling, extract: { ...polling.extract, expression: value } }),
                                        { label: 'Poll URL expression' },
                                    )}
                                </Field>
                                <Field label="Poll method">
                                    <select
                                        value={polling.method}
                                        disabled={readOnly}
                                        onChange={(event) => set('polling', { ...polling, method: event.target.value })}
                                    >
                                        {METHODS.map((method) => (
                                            <option key={method}>{method}</option>
                                        ))}
                                    </select>
                                </Field>
                                <Field label="Every (seconds)">
                                    <input
                                        type="number"
                                        min={0.5}
                                        max={3600}
                                        step={0.5}
                                        value={polling.interval}
                                        readOnly={readOnly}
                                        onChange={(event) => set('polling', { ...polling, interval: Number(event.target.value) || 1 })}
                                    />
                                </Field>
                                <Field label="At most (attempts)">
                                    <input
                                        type="number"
                                        min={1}
                                        max={1000}
                                        value={polling.max_attempts}
                                        readOnly={readOnly}
                                        onChange={(event) =>
                                            set('polling', { ...polling, max_attempts: Math.max(1, Math.round(Number(event.target.value) || 1)) })
                                        }
                                    />
                                </Field>
                                <div className="eagle-field-wide">
                                    <Toggle
                                        checked={polling.reuse_auth}
                                        disabled={readOnly}
                                        onChange={(value) => set('polling', { ...polling, reuse_auth: value })}
                                    >
                                        Send the same headers and auth with each poll
                                    </Toggle>
                                </div>
                                <Field label="Stop when" wide>
                                    <select
                                        value={polling.stop.type}
                                        disabled={readOnly}
                                        onChange={(event) =>
                                            set('polling', { ...polling, stop: { ...polling.stop, type: event.target.value as typeof polling.stop.type } })
                                        }
                                    >
                                        <option value="json">A JSON value is one of…</option>
                                        <option value="status">The HTTP status is not…</option>
                                        <option value="none">Only after the last attempt</option>
                                    </select>
                                </Field>
                                {polling.stop.type === 'json' && (
                                    <>
                                        <Field label="JSON path">
                                            {text(polling.stop.path, (value) => set('polling', { ...polling, stop: { ...polling.stop, path: value } }), {
                                                label: 'Stop JSON path',
                                                placeholder: 'status',
                                            })}
                                        </Field>
                                        <Field label="Values (comma separated)">
                                            {text(polling.stop.values, (value) => set('polling', { ...polling, stop: { ...polling.stop, values: value } }), {
                                                label: 'Stop values',
                                                placeholder: 'COMPLETED,FAILED',
                                            })}
                                        </Field>
                                    </>
                                )}
                                {polling.stop.type === 'status' && (
                                    <Field label="Keep polling while the status is">
                                        <input
                                            type="number"
                                            min={100}
                                            max={599}
                                            value={polling.stop.status}
                                            readOnly={readOnly}
                                            onChange={(event) =>
                                                set('polling', { ...polling, stop: { ...polling.stop, status: Number(event.target.value) || 202 } })
                                            }
                                        />
                                    </Field>
                                )}
                                <div className="eagle-field-wide">
                                    <Toggle
                                        checked={polling.stop.on_error}
                                        disabled={readOnly}
                                        onChange={(value) => set('polling', { ...polling, stop: { ...polling.stop, on_error: value } })}
                                    >
                                        Stop on an error status (4xx/5xx)
                                    </Toggle>
                                </div>
                            </>
                        )}
                    </div>
                )}

                {tab === 'options' && (
                    <div className="eagle-form">
                        <Field label="Timeout (seconds)" hint="1 to 300.">
                            <input
                                type="number"
                                min={1}
                                max={300}
                                value={draft.options.timeout}
                                readOnly={readOnly}
                                onChange={(event) => set('options', { ...draft.options, timeout: Number(event.target.value) || 30 })}
                            />
                        </Field>
                        <div className="eagle-field">
                            <span>Redirects</span>
                            <Toggle
                                checked={draft.options.follow_redirects}
                                disabled={readOnly}
                                onChange={(value) => set('options', { ...draft.options, follow_redirects: value })}
                            >
                                Follow redirects
                            </Toggle>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
