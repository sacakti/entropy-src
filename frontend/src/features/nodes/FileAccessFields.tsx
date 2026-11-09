import { Plus, Trash2 } from 'lucide-react'

import type { NodeFileAccess } from '../../api/runs.api'
import { fileAccessFor, fileAccessProblem, type Mode } from './fileAccess'

const MODES: { value: Mode; title: string; text: string }[] = [
    {
        value: 'off',
        title: 'Off',
        text: 'Paths are sent as they are; files must already be on the node.',
    },
    {
        value: 'fetch',
        title: 'Fetch from main',
        text: 'Files a run names are copied to the node before it starts, once per content.',
    },
    {
        value: 'shared',
        title: 'Shared folder',
        text: 'Both mount the same storage (NFS, SMB…); nothing is copied.',
    },
]

/**
 * How runs on a node reach files picked on the main node (a release package, say):
 * copied there before the run, or read from storage both mount.
 */
export default function FileAccessFields({
    value,
    onChange,
    installDir = '',
}: {
    value: NodeFileAccess
    onChange: (value: NodeFileAccess) => void
    /** The node's install directory, to suggest a workspace inside it. */
    installDir?: string
}) {
    const problem = fileAccessProblem(value)

    return (
        <div className="node-file-access admin-field-wide">
            <div className="node-file-modes" role="radiogroup" aria-label="File access">
                {MODES.map((mode) => (
                    <button
                        key={mode.value}
                        type="button"
                        role="radio"
                        aria-checked={value.mode === mode.value}
                        className={`node-file-mode${value.mode === mode.value ? ' is-selected' : ''}`}
                        onClick={() => onChange(fileAccessFor(mode.value, value, installDir))}
                    >
                        <strong>{mode.title}</strong>
                        <small>{mode.text}</small>
                    </button>
                ))}
            </div>

            {value.mode === 'fetch' && (
                <div className="admin-form-grid">
                    <label className="admin-field admin-field-wide">
                        <span>Workspace folder on the node</span>
                        <input
                            value={value.workspace}
                            onChange={(event) => onChange({ ...value, workspace: event.target.value })}
                            placeholder="/home/deploy/.entropy-agent/workspace/files"
                            spellCheck={false}
                        />
                        <small className="node-field-hint">
                            Copies are kept here and reused while their content is the same. Setting the node up
                            creates it.
                        </small>
                    </label>
                    <div className="admin-field admin-field-wide">
                        <span>Send files from these main-node folders</span>
                        {value.sources.map((source, index) => (
                            <div key={index} className="node-file-row">
                                <input
                                    value={source}
                                    onChange={(event) =>
                                        onChange({
                                            ...value,
                                            sources: value.sources.map((item, position) =>
                                                position === index ? event.target.value : item,
                                            ),
                                        })
                                    }
                                    placeholder="/opt/releases"
                                    spellCheck={false}
                                    aria-label={`Folder ${index + 1} to send files from`}
                                />
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                    aria-label="Remove folder"
                                    onClick={() =>
                                        onChange({ ...value, sources: value.sources.filter((_, position) => position !== index) })
                                    }
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))}
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm node-file-add"
                            disabled={value.sources.length >= 10}
                            onClick={() => onChange({ ...value, sources: [...value.sources, ''] })}
                        >
                            <Plus size={14} /> Add folder
                        </button>
                        <small className="node-field-hint">
                            {value.sources.length
                                ? 'Only files in these folders are copied; other paths (an Oracle home, say) are left for the node’s own.'
                                : 'None listed: uploaded artifacts and the Entropy workspace. Other paths are left as they are.'}
                        </small>
                    </div>
                    <label className="admin-field">
                        <span>Most per run (GB)</span>
                        <input
                            type="number"
                            min={1}
                            max={1000}
                            value={value.max_gb}
                            onChange={(event) => onChange({ ...value, max_gb: Number(event.target.value) })}
                        />
                    </label>
                </div>
            )}

            {value.mode === 'shared' && (
                <div className="admin-field admin-field-wide">
                    <span>Shared folders: on the main node, and where this node mounts it</span>
                    {value.mappings.map((pair, index) => (
                        <div key={index} className="node-file-row is-pair">
                            <input
                                value={pair.main}
                                onChange={(event) =>
                                    onChange({
                                        ...value,
                                        mappings: value.mappings.map((item, position) =>
                                            position === index ? { ...item, main: event.target.value } : item,
                                        ),
                                    })
                                }
                                placeholder="Main: /mnt/entropy-share"
                                spellCheck={false}
                                aria-label={`Shared folder ${index + 1} on the main node`}
                            />
                            <span aria-hidden="true">→</span>
                            <input
                                value={pair.node}
                                onChange={(event) =>
                                    onChange({
                                        ...value,
                                        mappings: value.mappings.map((item, position) =>
                                            position === index ? { ...item, node: event.target.value } : item,
                                        ),
                                    })
                                }
                                placeholder="Node: /data/entropy-share"
                                spellCheck={false}
                                aria-label={`Shared folder ${index + 1} on this node`}
                            />
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="Remove shared folder"
                                disabled={value.mappings.length === 1}
                                onClick={() =>
                                    onChange({ ...value, mappings: value.mappings.filter((_, position) => position !== index) })
                                }
                            >
                                <Trash2 size={14} />
                            </button>
                        </div>
                    ))}
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-sm node-file-add"
                        disabled={value.mappings.length >= 10}
                        onClick={() => onChange({ ...value, mappings: [...value.mappings, { main: '', node: '' }] })}
                    >
                        <Plus size={14} /> Add shared folder
                    </button>
                    <small className="node-field-hint">
                        Mount the same share on both servers first (e.g. NFS in /etc/fstab). Setting the node up checks
                        each folder is mounted; a run whose files are on the main node but not in a shared folder is
                        refused before it starts.
                    </small>
                </div>
            )}

            {problem && value.mode !== 'off' && <small className="node-field-warning">{problem}</small>}
        </div>
    )
}
