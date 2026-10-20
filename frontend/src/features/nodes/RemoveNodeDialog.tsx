import { useState } from 'react'
import { AlertCircle, LoaderCircle, Trash2 } from 'lucide-react'

import { nodesApi, type EntropyNode, type NodeCredentials } from '../../api/runs.api'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from '../runs/format'
import CredentialsFields from './CredentialsFields'
import { credentialsReady } from './credentials'
import ProvisioningLog from './ProvisioningLog'

/** Remove a node, optionally uninstalling its agent over SSH. */
export default function RemoveNodeDialog({
    node,
    onClose,
    onRemoved,
}: {
    node: EntropyNode
    onClose: () => void
    onRemoved: () => void
}) {
    const [uninstall, setUninstall] = useState(false)
    const [credentials, setCredentials] = useState<NodeCredentials>({ auth: 'password' })
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [recordId, setRecordId] = useState<number | null>(null)
    const [finished, setFinished] = useState(false)

    const submit = async () => {
        setBusy(true)
        setError(null)
        try {
            const result = await nodesApi.remove(node.name, { ...credentials, uninstall })
            setCredentials({ auth: credentials.auth })
            if (result.provisioning_id) {
                setRecordId(result.provisioning_id)
            } else {
                onRemoved()
                onClose()
            }
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to remove the node.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title={`Remove ${node.name}?`}
            subtitle="Its token is revoked at once, so the agent stops. Runs still active on it fail."
            icon={<Trash2 size={18} />}
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
                            className="entropy-button entropy-button-danger"
                            onClick={() => void submit()}
                            disabled={busy || (uninstall && !credentialsReady(credentials))}
                        >
                            {busy && <LoaderCircle size={15} className="entropy-spin" />}
                            {uninstall ? 'Uninstall and remove' : 'Remove node'}
                        </button>
                    </>
                ) : (
                    <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
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
                        onRemoved()
                    }}
                />
            ) : (
                <div className="admin-form-grid">
                    <div className="start-run-nodes admin-field-wide" role="radiogroup" aria-label="Removal">
                        <label className={`start-run-node${!uninstall ? ' is-selected' : ''}`}>
                            <input type="radio" checked={!uninstall} onChange={() => setUninstall(false)} />
                            <span>
                                <strong>Remove from Entropy</strong>
                                <small>The agent stops; its files stay in {node.install_dir || 'the install directory'}.</small>
                            </span>
                        </label>
                        <label className={`start-run-node${uninstall ? ' is-selected' : ''}`}>
                            <input type="radio" checked={uninstall} onChange={() => setUninstall(true)} />
                            <span>
                                <strong>Also uninstall from the server</strong>
                                <small>Signs in over SSH to stop the service and delete the agent's files.</small>
                            </span>
                        </label>
                    </div>
                    {uninstall && <CredentialsFields value={credentials} onChange={setCredentials} />}
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
