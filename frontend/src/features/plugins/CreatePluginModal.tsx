import { useEffect, useState } from 'react'
import { CheckCircle2, LoaderCircle, Plus, X, XCircle } from 'lucide-react'

import { pluginsApi, type PluginItem } from '../../api/plugins.api'
import { useErrorToast } from '../../components/feedback/useToast'

const NAME_PATTERN = /^[a-z][a-z0-9_]*$/
const CHECK_DELAY = 350

type Availability =
    | { state: 'idle' }
    | { state: 'checking' }
    | { state: 'available' }
    | { state: 'unavailable'; reason: string }

function localProblem(namespace: string, name: string): string | null {
    if (!namespace || !name) return null
    if (!NAME_PATTERN.test(namespace)) {
        return 'Namespace must start with a lowercase letter and use only a-z, 0-9 and _.'
    }
    if (!NAME_PATTERN.test(name)) {
        return 'Name must start with a lowercase letter and use only a-z, 0-9 and _.'
    }
    return null
}

export default function CreatePluginModal({
    onClose,
    onCreated,
}: {
    onClose: () => void
    /** `visual`: the plugin is made in the no-code builder. */
    onCreated: (plugin: PluginItem, visual: boolean) => void
}) {
    const [namespace, setNamespace] = useState('custom')
    const [name, setName] = useState('')
    const [description, setDescription] = useState('')
    const [visual, setVisual] = useState(false)
    const [availability, setAvailability] = useState<Availability>({ state: 'idle' })
    const [creating, setCreating] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)

    const trimmedNamespace = namespace.trim()
    const trimmedName = name.trim()
    const problem = localProblem(trimmedNamespace, trimmedName)

    useEffect(() => {
        if (!trimmedNamespace || !trimmedName || problem) return

        let active = true
        const timer = window.setTimeout(() => {
            setAvailability({ state: 'checking' })

            pluginsApi
                .availability(trimmedNamespace, trimmedName)
                .then((result) => {
                    if (!active) return
                    setAvailability(
                        result.available
                            ? { state: 'available' }
                            : {
                                  state: 'unavailable',
                                  reason: result.reason ?? 'Unavailable.',
                              },
                    )
                })
                .catch((cause: unknown) => {
                    if (!active) return
                    setAvailability({
                        state: 'unavailable',
                        reason:
                            cause instanceof Error
                                ? cause.message
                                : 'Unable to check availability.',
                    })
                })
        }, CHECK_DELAY)

        return () => {
            active = false
            window.clearTimeout(timer)
        }
    }, [trimmedNamespace, trimmedName, problem])

    useEffect(() => {
        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape' && !creating) onClose()
        }

        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [creating, onClose])

    const status: Availability = problem
        ? { state: 'unavailable', reason: problem }
        : !trimmedNamespace || !trimmedName
          ? { state: 'idle' }
          : availability

    const canCreate = status.state === 'available' && !creating

    const submit = async () => {
        if (!canCreate) return

        setCreating(true)
        setError(null)

        try {
            const plugin = await pluginsApi.create({
                namespace: trimmedNamespace,
                name: trimmedName,
                description: description.trim(),
            })
            onCreated(plugin, visual)
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : 'Unable to create plugin.')
            setCreating(false)
        }
    }

    return (
        <div
            className="plugins-modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget && !creating) onClose()
            }}
        >
            <form
                className="plugins-details-modal plugins-create-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="plugins-create-title"
                onSubmit={(event) => {
                    event.preventDefault()
                    void submit()
                }}
            >
                <header className="plugins-modal-heading">
                    <div>
                        <p className="page-eyebrow">NEW PLUGIN</p>
                        <h2 id="plugins-create-title">Create plugin</h2>
                    </div>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label="Close"
                        onClick={onClose}
                        disabled={creating}
                    >
                        <X size={18} />
                    </button>
                </header>

                <p className="plugins-create-help">
                    The plugin is generated from the Entropy plugin template
                    (plugin.py, plugin.json, README.md, MAN.md, workflow.json…)
                    and saved as a draft. Workflows can use it once you install it.
                </p>

                <div className="plugins-create-grid">
                    <label className="plugins-field">
                        <span>Namespace</span>
                        <input
                            autoFocus
                            value={namespace}
                            onChange={(event) => setNamespace(event.target.value)}
                            placeholder="custom"
                            maxLength={64}
                            spellCheck={false}
                            autoComplete="off"
                        />
                    </label>
                    <label className="plugins-field">
                        <span>Name</span>
                        <input
                            value={name}
                            onChange={(event) => setName(event.target.value)}
                            placeholder="my_plugin"
                            maxLength={64}
                            spellCheck={false}
                            autoComplete="off"
                        />
                    </label>
                </div>

                <div
                    className={`plugins-availability plugins-availability-${status.state}`}
                    role="status"
                    aria-live="polite"
                >
                    {status.state === 'checking' && (
                        <>
                            <LoaderCircle size={15} className="entropy-spin" />
                            Checking {trimmedNamespace}.{trimmedName}…
                        </>
                    )}
                    {status.state === 'available' && (
                        <>
                            <CheckCircle2 size={15} />
                            {trimmedNamespace}.{trimmedName} is available.
                        </>
                    )}
                    {status.state === 'unavailable' && (
                        <>
                            <XCircle size={15} />
                            {status.reason}
                        </>
                    )}
                    {status.state === 'idle' && 'Enter a namespace and a name.'}
                </div>

                <label className="plugins-field">
                    <span>Description (optional)</span>
                    <input
                        value={description}
                        onChange={(event) => setDescription(event.target.value)}
                        placeholder="What does this plugin do?"
                        maxLength={200}
                    />
                </label>

                <fieldset className="plugins-field plugins-dev-style">
                    <legend>How will you build it?</legend>
                    <label className={!visual ? 'is-selected' : ''}>
                        <input type="radio" name="dev-style" checked={!visual} onChange={() => setVisual(false)} />
                        <span>
                            <strong>Source code</strong>
                            <small>Write Python in the editor; anything the Plugin SDK can do.</small>
                        </span>
                    </label>
                    <label className={visual ? 'is-selected' : ''}>
                        <input type="radio" name="dev-style" checked={visual} onChange={() => setVisual(true)} />
                        <span>
                            <strong>Visual builder (no code)</strong>
                            <small>Inputs, outputs and steps from blocks; Entropy writes the Python for you.</small>
                        </span>
                    </label>
                </fieldset>


                <footer className="plugins-modal-footer">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={onClose}
                        disabled={creating}
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        className="entropy-button entropy-button-primary"
                        disabled={!canCreate}
                    >
                        {creating ? (
                            <LoaderCircle size={16} className="entropy-spin" />
                        ) : (
                            <Plus size={16} />
                        )}
                        {creating ? 'Creating…' : 'Create plugin'}
                    </button>
                </footer>
            </form>
        </div>
    )
}
