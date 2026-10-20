import { useEffect, useState } from 'react'
import { AlertCircle, ChevronDown, LoaderCircle, ServerCog } from 'lucide-react'

import {
    nodesApi,
    type EntropyNode,
    type NodeCredentials,
    type NodeSetupInput,
    type ServerAddress,
} from '../../api/runs.api'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from '../runs/format'
import CredentialsFields from './CredentialsFields'
import { credentialsReady } from './credentials'
import ProvisioningLog from './ProvisioningLog'

const NAME = /^[a-z0-9][a-z0-9._-]{0,62}$/

/** A host that means "this machine": localhost, 127.x.x.x, ::1, 0.0.0.0. */
function isLoopbackHost(host: string): boolean {
    const name = host.trim().toLowerCase().replace(/^\[|\]$/g, '')
    return name === 'localhost' || name === '::1' || name === '0.0.0.0' || /^127\./.test(name)
}

function isLoopback(url: string): boolean {
    try {
        return isLoopbackHost(new URL(url).hostname)
    } catch {
        return false
    }
}

/**
 * Add a node, or set an existing one up again, over SSH; then follow the
 * setup live.
 */
export default function NodeSetupDialog({
    node,
    onClose,
    onDone,
}: {
    node: EntropyNode | null
    onClose: () => void
    onDone: () => void
}) {
    const [values, setValues] = useState<Omit<NodeSetupInput, keyof NodeCredentials>>(() => ({
        name: node?.name ?? '',
        host: node?.host ?? '',
        port: node?.port ?? 22,
        ssh_user: node?.ssh_user ?? '',
        server_url: node?.server_url ?? window.location.origin,
        verify_tls: true,
        ca_cert: '',
        python: 'auto',
        install_dir: node?.install_dir || '~/.entropy-agent',
        max_jobs: node?.max_jobs ?? 2,
        description: node?.description ?? '',
        install_cli: true,
    }))
    const [credentials, setCredentials] = useState<NodeCredentials>({ auth: 'password' })
    const [advanced, setAdvanced] = useState(false)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [recordId, setRecordId] = useState<number | null>(null)
    const [finished, setFinished] = useState(false)

    const set = (patch: Partial<typeof values>) => setValues((current) => ({ ...current, ...patch }))

    // How the node can reach this server; replaces a "localhost" default.
    const [server, setServer] = useState<ServerAddress | null>(null)
    useEffect(() => {
        let active = true
        nodesApi
            .serverAddress()
            .then((result) => {
                if (!active) return
                setServer(result)
                const better = result.suggestions[0]
                if (better) {
                    setValues((current) =>
                        isLoopback(current.server_url)
                            ? { ...current, server_url: better }
                            : current,
                    )
                }
            })
            .catch(() => undefined)
        return () => {
            active = false
        }
    }, [])

    const insecure = values.server_url.startsWith('http://') && !isLoopback(values.server_url)
    // On the node, a loopback address is the node itself.
    const unreachable = isLoopback(values.server_url) && !isLoopbackHost(values.host)
    const ready =
        !unreachable &&
        NAME.test(values.name) &&
        values.name !== 'local' &&
        values.host.trim() !== '' &&
        values.ssh_user.trim() !== '' &&
        /^https?:\/\//.test(values.server_url) &&
        credentialsReady(credentials)

    const submit = async () => {
        setSubmitting(true)
        setError(null)
        try {
            const payload: NodeSetupInput = { ...values, ...credentials, port: Number(values.port) }
            const result = node ? await nodesApi.setup(payload) : await nodesApi.add(payload)
            // Credentials are not kept once the setup has them.
            setCredentials({ auth: credentials.auth })
            setRecordId(result.provisioning_id)
            onDone()
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to start the setup.'))
        } finally {
            setSubmitting(false)
        }
    }

    const title = node ? `Set up ${node.name} again` : 'Add node'

    return (
        <Dialog
            title={title}
            subtitle={
                recordId === null
                    ? 'Entropy connects over SSH once, installs Python if needed and the agent, then the node connects back on its own.'
                    : `${values.ssh_user}@${values.host}:${values.port}`
            }
            icon={<ServerCog size={18} />}
            onClose={onClose}
            className="node-setup-dialog"
            footer={
                recordId === null ? (
                    <>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Cancel
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            onClick={() => void submit()}
                            disabled={!ready || submitting}
                        >
                            {submitting && <LoaderCircle size={15} className="entropy-spin" />}
                            {node ? 'Set up again' : 'Add and set up'}
                        </button>
                    </>
                ) : (
                    <button
                        type="button"
                        className={`entropy-button ${finished ? 'entropy-button-primary' : 'entropy-button-secondary'}`}
                        onClick={onClose}
                    >
                        {finished ? 'Done' : 'Continue in background'}
                    </button>
                )
            }
        >
            {recordId !== null ? (
                <ProvisioningLog
                    id={recordId}
                    onFinished={() => {
                        setFinished(true)
                        onDone()
                    }}
                />
            ) : (
                <div className="admin-form-grid">
                    <label className="admin-field">
                        <span>Node name</span>
                        <input
                            value={values.name}
                            onChange={(event) => set({ name: event.target.value.toLowerCase() })}
                            placeholder="build-01"
                            disabled={Boolean(node)}
                            maxLength={63}
                        />
                        {values.name && !NAME.test(values.name) && (
                            <small className="node-field-error">Lowercase letters, digits, '.', '_' or '-'.</small>
                        )}
                    </label>
                    <label className="admin-field">
                        <span>Description</span>
                        <input
                            value={values.description}
                            onChange={(event) => set({ description: event.target.value })}
                            placeholder="Optional"
                            maxLength={500}
                        />
                    </label>

                    <label className="admin-field">
                        <span>Host</span>
                        <input
                            value={values.host}
                            onChange={(event) => set({ host: event.target.value.trim() })}
                            placeholder="build-01.example.com"
                            spellCheck={false}
                        />
                    </label>
                    <div className="node-host-row">
                        <label className="admin-field">
                            <span>SSH port</span>
                            <input
                                type="number"
                                min={1}
                                max={65535}
                                value={values.port}
                                onChange={(event) => set({ port: Number(event.target.value) })}
                            />
                        </label>
                        <label className="admin-field">
                            <span>SSH user</span>
                            <input
                                value={values.ssh_user}
                                onChange={(event) => set({ ssh_user: event.target.value.trim() })}
                                placeholder="deploy"
                                autoComplete="off"
                                spellCheck={false}
                            />
                        </label>
                    </div>

                    <CredentialsFields value={credentials} onChange={setCredentials} showForgetHostKey={Boolean(node)} />

                    <label className="admin-field admin-field-wide">
                        <span>Main node URL (as the node reaches it)</span>
                        <input
                            value={values.server_url}
                            onChange={(event) => set({ server_url: event.target.value.trim() })}
                            spellCheck={false}
                        />
                        {unreachable && (
                            <small className="node-field-warning">
                                On the node, this address is the node itself. Use an address of this server the node
                                can reach.
                            </small>
                        )}
                        {server && !server.local_only && server.suggestions.length > 0 && (
                            <span className="node-url-suggestions">
                                This server:{' '}
                                {server.suggestions.slice(0, 4).map((url) => (
                                    <button
                                        key={url}
                                        type="button"
                                        className={`run-tag${url === values.server_url ? ' is-active' : ''}`}
                                        onClick={() => set({ server_url: url })}
                                    >
                                        {url}
                                    </button>
                                ))}
                            </span>
                        )}
                        {server?.local_only && (
                            <small className="node-field-warning" role="alert">
                                {server.advice}
                            </small>
                        )}
                        {insecure && (
                            <small className="node-field-warning">
                                Unencrypted HTTP sends the node token in clear text. Prefer https://.
                            </small>
                        )}
                    </label>

                    <button
                        type="button"
                        className="node-advanced-toggle"
                        aria-expanded={advanced}
                        onClick={() => setAdvanced((value) => !value)}
                    >
                        <ChevronDown size={14} aria-hidden="true" /> Advanced
                    </button>

                    {advanced && (
                        <>
                            <label className="admin-field">
                                <span>Python</span>
                                <select
                                    className="schedule-select"
                                    value={values.python}
                                    onChange={(event) => set({ python: event.target.value as NodeSetupInput['python'] })}
                                >
                                    <option value="auto">Server's Python 3.9 if present, else bundled</option>
                                    <option value="system">Always the server's Python</option>
                                    <option value="bundled">Always the bundled Python 3.9</option>
                                </select>
                            </label>
                            <label className="admin-field">
                                <span>Concurrent runs</span>
                                <input
                                    type="number"
                                    min={1}
                                    max={64}
                                    value={values.max_jobs}
                                    onChange={(event) => set({ max_jobs: Number(event.target.value) })}
                                />
                            </label>
                            <label className="admin-field admin-field-wide">
                                <span>Install directory</span>
                                <input
                                    value={values.install_dir}
                                    onChange={(event) => set({ install_dir: event.target.value.trim() })}
                                    spellCheck={false}
                                />
                            </label>
                            <label className="admin-field admin-field-wide">
                                <span>CA certificate for the main node (PEM, optional)</span>
                                <textarea
                                    rows={3}
                                    spellCheck={false}
                                    value={values.ca_cert}
                                    onChange={(event) => set({ ca_cert: event.target.value })}
                                    placeholder="-----BEGIN CERTIFICATE-----"
                                />
                            </label>
                            <label className="schedule-switch admin-field-wide">
                                <input
                                    type="checkbox"
                                    checked={values.verify_tls}
                                    onChange={(event) => set({ verify_tls: event.target.checked })}
                                />
                                Verify the main node's TLS certificate
                            </label>
                            <label className="schedule-switch admin-field-wide">
                                <input
                                    type="checkbox"
                                    checked={values.install_cli}
                                    onChange={(event) => set({ install_cli: event.target.checked })}
                                />
                                Install the ent command line (users on the node run ent login, ent job …)
                            </label>
                        </>
                    )}

                    {error && (
                        <div className="entropy-alert entropy-alert-error admin-field-wide" role="alert">
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                    )}
                </div>
            )}
        </Dialog>
    )
}
