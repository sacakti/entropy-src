import { useEffect, useMemo, useState } from 'react'
import {
    ArrowLeft,
    BookOpen,
    Check,
    Copy,
    FileInput,
    FileOutput,
    Package,
    Pencil,
    Play,
    Workflow as WorkflowIcon,
} from 'lucide-react'
import { dump } from 'js-yaml'

import { getPluginDocs, type PluginArgumentSpec, type PluginDocs } from '../../api/plugins.api'
import WallpaperLayer from '../preferences/WallpaperLayer'
import { useShortcuts } from '../../components/layout/useShortcuts'
import '../../styles/plugin-help.css'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

const TYPE_HINT: Record<string, string> = {
    string: 'Text',
    boolean: 'true or false',
    integer: 'Whole number',
    number: 'Number',
    list: 'List of values',
    dictionary: 'Key/value map',
    dict: 'Key/value map',
    any: 'Any value',
}

function describeRange(argument: PluginArgumentSpec): string {
    const { minimum, maximum } = argument
    if (minimum !== undefined && maximum !== undefined) return `${minimum} to ${maximum}`
    if (minimum !== undefined) return `at least ${minimum}`
    if (maximum !== undefined) return `at most ${maximum}`
    return ''
}

function formatDefault(value: unknown): string {
    if (value === null || value === undefined) return '—'
    return typeof value === 'string' ? value : JSON.stringify(value)
}

function CopyButton({ text, label }: { text: string; label: string }) {
    const [copied, setCopied] = useState(false)
    return (
        <button
            type="button"
            className="entropy-button entropy-button-ghost entropy-button-sm"
            onClick={() => {
                void navigator.clipboard
                    .writeText(text)
                    .then(() => {
                        setCopied(true)
                        window.setTimeout(() => setCopied(false), 1500)
                    })
                    .catch(() => undefined)
            }}
        >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copied' : label}
        </button>
    )
}

/**
 * A plugin's help page: what it does, the arguments it takes, the outputs
 * later steps can use, a ready-to-paste workflow step, its manual, and the
 * workflows that use it.
 */
export default function PluginHelp({
    qualifiedName,
    onClose,
    onRun,
    onEdit,
    runReason,
    editLabel,
}: {
    qualifiedName: string
    onClose: () => void
    onRun?: () => void
    onEdit?: () => void
    /** Why the plugin cannot be run, or null when it can. */
    runReason: string | null
    editLabel: string
}) {
    const [docs, setDocs] = useState<PluginDocs | null>(null)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)

    useEffect(() => {
        let active = true
        getPluginDocs(qualifiedName)
            .then((result) => {
                if (active) setDocs(result)
            })
            .catch((cause: unknown) => {
                if (active) setError(cause instanceof Error ? cause.message : 'Unable to load the plugin help.')
            })
        return () => {
            active = false
        }
    }, [qualifiedName])

    useShortcuts({ escape: onClose }, true)

    const usageYaml = useMemo(
        () => (docs ? dump({ steps: [docs.usage] }, { lineWidth: -1, noRefs: true, indent: 2 }) : ''),
        [docs],
    )
    const stepName = typeof docs?.usage.name === 'string' ? docs.usage.name : 'step'
    const required = docs?.arguments.filter((argument) => argument.required) ?? []
    const optional = docs?.arguments.filter((argument) => !argument.required) ?? []

    const sections = [
        { id: 'overview', label: 'Overview' },
        { id: 'inputs', label: 'Inputs' },
        { id: 'outputs', label: 'Outputs' },
        { id: 'usage', label: 'Use in a workflow' },
        ...(docs?.manual ? [{ id: 'manual', label: 'Manual' }] : []),
        ...(docs && docs.used_by.length > 0 ? [{ id: 'used-by', label: 'Used by' }] : []),
    ]

    const argumentRows = (items: PluginArgumentSpec[]) =>
        items.map((argument) => (
            <tr key={argument.name}>
                <td>
                    <code>{argument.name}</code>
                </td>
                <td>{TYPE_HINT[argument.type] ?? argument.type}</td>
                <td>{formatDefault(argument.default)}</td>
                <td>{describeRange(argument) || '—'}</td>
            </tr>
        ))

    return (
        <div className="plugin-help" role="dialog" aria-modal="true" aria-label={`${qualifiedName} help`}>
            <WallpaperLayer veil="var(--app-bg)" />
            <header className="plugin-help-topbar">
                <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                    <ArrowLeft size={16} />
                    Plugins
                </button>
                <div className="plugin-help-actions">
                    {onEdit && (
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onEdit}>
                            <Pencil size={15} />
                            {editLabel}
                        </button>
                    )}
                    {onRun && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            onClick={() => {
                                if (!runReason) onRun()
                            }}
                            aria-disabled={runReason ? true : undefined}
                            title={runReason ?? 'Run the plugin once'}
                        >
                            <Play size={15} />
                            Test run
                        </button>
                    )}
                </div>
            </header>

            {error ? (
                <p className="entropy-unavailable">Not available.</p>
            ) : !docs ? (
                <EntropyLoader label="Loading help…" />
            ) : (
                <div className="plugin-help-layout">
                    <nav className="plugin-help-nav" aria-label="Sections">
                        {sections.map((section) => (
                            <a key={section.id} href={`#plugin-help-${section.id}`} onClick={(event) => {
                                event.preventDefault()
                                document
                                    .getElementById(`plugin-help-${section.id}`)
                                    ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                            }}>
                                {section.label}
                            </a>
                        ))}
                    </nav>

                    <main className="plugin-help-main">
                        <section id="plugin-help-overview" className="plugin-help-hero">
                            <span className="plugin-help-icon" aria-hidden="true">
                                <Package size={26} />
                            </span>
                            <div>
                                <h1>{docs.name}</h1>
                                <p className="plugin-help-qualified">
                                    <code>{docs.qualified_name}</code> · version {docs.version}
                                    {docs.draft ? ' · draft (not installed)' : docs.enabled ? '' : ' · disabled'}
                                </p>
                                <p className="plugin-help-description">
                                    {docs.description || 'No description.'}
                                </p>
                                <dl className="plugin-help-facts">
                                    {docs.author && (
                                        <div>
                                            <dt>Author</dt>
                                            <dd>{docs.author}</dd>
                                        </div>
                                    )}
                                    {docs.entropy && (
                                        <div>
                                            <dt>Entropy</dt>
                                            <dd>{docs.entropy}</dd>
                                        </div>
                                    )}
                                    {docs.license && (
                                        <div>
                                            <dt>License</dt>
                                            <dd>{docs.license}</dd>
                                        </div>
                                    )}
                                    {docs.dependencies.length > 0 && (
                                        <div>
                                            <dt>Needs</dt>
                                            <dd>{docs.dependencies.join(', ')}</dd>
                                        </div>
                                    )}
                                    {docs.tags.length > 0 && (
                                        <div>
                                            <dt>Tags</dt>
                                            <dd className="plugin-help-tags">
                                                {docs.tags.map((tag) => (
                                                    <span key={tag} className="list-chip">
                                                        {tag}
                                                    </span>
                                                ))}
                                            </dd>
                                        </div>
                                    )}
                                </dl>
                            </div>
                        </section>

                        <section id="plugin-help-inputs" className="plugin-help-card">
                            <h2>
                                <FileInput size={17} /> Inputs
                            </h2>
                            <p className="plugin-help-lead">
                                Arguments go under <code>arguments:</code> in the step. Values can use workflow variables
                                (<code>{'${name}'}</code>), vault secrets and outputs of earlier steps.
                            </p>
                            {docs.arguments.length === 0 ? (
                                <p className="plugin-help-muted">This plugin takes no arguments.</p>
                            ) : (
                                <>
                                    <h3>Required</h3>
                                    {required.length === 0 ? (
                                        <p className="plugin-help-muted">None: every argument has a default.</p>
                                    ) : (
                                        <table className="plugin-help-table">
                                            <thead>
                                                <tr>
                                                    <th>Argument</th>
                                                    <th>Type</th>
                                                    <th>Default</th>
                                                    <th>Allowed</th>
                                                </tr>
                                            </thead>
                                            <tbody>{argumentRows(required)}</tbody>
                                        </table>
                                    )}
                                    {optional.length > 0 && (
                                        <>
                                            <h3>Optional</h3>
                                            <table className="plugin-help-table">
                                                <thead>
                                                    <tr>
                                                        <th>Argument</th>
                                                        <th>Type</th>
                                                        <th>Default</th>
                                                        <th>Allowed</th>
                                                    </tr>
                                                </thead>
                                                <tbody>{argumentRows(optional)}</tbody>
                                            </table>
                                        </>
                                    )}
                                </>
                            )}
                        </section>

                        <section id="plugin-help-outputs" className="plugin-help-card">
                            <h2>
                                <FileOutput size={17} /> Outputs
                            </h2>
                            {docs.outputs.length === 0 ? (
                                <p className="plugin-help-muted">
                                    This plugin publishes no outputs; later steps can only rely on whether it succeeded.
                                </p>
                            ) : (
                                <>
                                    <p className="plugin-help-lead">
                                        After the step runs, later steps read these values. With the step named{' '}
                                        <code>{stepName}</code>:
                                    </p>
                                    <table className="plugin-help-table">
                                        <thead>
                                            <tr>
                                                <th>Output</th>
                                                <th>Use it in a later step as</th>
                                                <th />
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {docs.outputs.map((output) => {
                                                const reference = `\${steps.${stepName}.outputs.${output}}`
                                                return (
                                                    <tr key={output}>
                                                        <td>
                                                            <code>{output}</code>
                                                        </td>
                                                        <td>
                                                            <code>{reference}</code>
                                                        </td>
                                                        <td className="plugin-help-copy-cell">
                                                            <CopyButton text={reference} label="Copy" />
                                                        </td>
                                                    </tr>
                                                )
                                            })}
                                        </tbody>
                                    </table>
                                </>
                            )}
                            <p className="plugin-help-muted">
                                Every step also succeeds or fails; with <code>on_failure: abort</code> a failure stops the
                                workflow, with <code>continue</code> the next steps still run.
                            </p>
                        </section>

                        <section id="plugin-help-usage" className="plugin-help-card">
                            <div className="plugin-help-card-head">
                                <h2>
                                    <WorkflowIcon size={17} /> Use in a workflow
                                </h2>
                                <CopyButton text={usageYaml} label="Copy YAML" />
                            </div>
                            <p className="plugin-help-lead">
                                {docs.usage_from_example
                                    ? "A step from the plugin's own example workflow. Paste it under steps in the workflow builder's YAML view."
                                    : 'A step with every required argument. Replace the placeholder values and paste it under steps in the workflow builder’s YAML view.'}
                            </p>
                            <pre className="plugin-help-code">
                                <code>{usageYaml}</code>
                            </pre>
                        </section>

                        {docs.manual && (
                            <section id="plugin-help-manual" className="plugin-help-card">
                                <h2>
                                    <BookOpen size={17} /> Manual
                                    <small>{docs.manual.file}</small>
                                </h2>
                                {/* Rendered on the server with raw HTML disabled and unsafe links removed. */}
                                <div
                                    className="plugin-help-manual"
                                    dangerouslySetInnerHTML={{ __html: docs.manual.html }}
                                />
                            </section>
                        )}

                        {docs.used_by.length > 0 && (
                            <section id="plugin-help-used-by" className="plugin-help-card">
                                <h2>
                                    <WorkflowIcon size={17} /> Used by
                                </h2>
                                <ul className="plugin-help-used-by">
                                    {docs.used_by.map((workflow) => (
                                        <li key={workflow.name}>
                                            <strong>{workflow.name}</strong>
                                            <span className="list-version">{workflow.version}</span>
                                            <span className="plugin-help-muted">
                                                step{workflow.steps.length === 1 ? '' : 's'} {workflow.steps.join(', ')}
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </section>
                        )}
                    </main>
                </div>
            )}
        </div>
    )
}
