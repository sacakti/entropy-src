import { useState } from 'react'
import { FolderSync, LoaderCircle } from 'lucide-react'

import { nodesApi, type EntropyNode, type NodeFileAccess } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from '../runs/format'
import FileAccessFields from './FileAccessFields'
import { cleanFileAccess, fileAccessProblem } from './fileAccess'

/**
 * Change how runs on a node reach the main node's files, without setting it up again.
 * The folders are checked when the node is next set up, and by each run that uses them.
 */
export default function FileAccessDialog({
    node,
    onClose,
    onSaved,
}: {
    node: EntropyNode
    onClose: () => void
    onSaved: () => void
}) {
    const { notify } = useFeedback()
    const [value, setValue] = useState<NodeFileAccess>(node.file_access ?? { mode: 'off' })
    const [saving, setSaving] = useState(false)
    const problem = fileAccessProblem(value)

    const save = async () => {
        setSaving(true)
        try {
            await nodesApi.setFileAccess(node.name, cleanFileAccess(value))
            notify.success(`File access of ${node.name} saved.`)
            onSaved()
            onClose()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to save the file access.'), { title: node.name })
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={`Files for runs on ${node.name}`}
            subtitle="How runs here reach files picked on the main node, such as a release package. Applies to runs started from now on."
            icon={<FolderSync size={18} />}
            onClose={onClose}
            className="node-setup-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        disabled={saving || problem !== null}
                        onClick={() => void save()}
                    >
                        {saving && <LoaderCircle size={15} className="entropy-spin" />}
                        Save
                    </button>
                </>
            }
        >
            <div className="admin-form-grid">
                <FileAccessFields value={value} onChange={setValue} installDir={node.install_dir} />
                {value.mode === 'fetch' && (
                    <small className="node-field-hint admin-field-wide">
                        The node creates the workspace folder when it first copies a file. Choose Set up again to
                        create and check it now.
                    </small>
                )}
                {value.mode === 'shared' && (
                    <small className="node-field-hint admin-field-wide">
                        Choose Set up again to check the folders are mounted on the node now; otherwise the first run
                        that uses them checks.
                    </small>
                )}
            </div>
        </Dialog>
    )
}
