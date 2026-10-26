import { useState } from 'react'
import { KeyRound, LoaderCircle, MessageSquareText, Send } from 'lucide-react'

import { runsApi, type RunPrompt } from '../../api/runs.api'
import { errorMessage } from './format'

/** Questions an interactive run waits on, each with its answer form. */
export default function RunPrompts({
    runId,
    prompts,
    onAnswered,
}: {
    runId: number
    prompts: RunPrompt[]
    onAnswered: (prompt: RunPrompt) => void
}) {
    if (!prompts.length) return null

    return (
        <section className="run-prompts" aria-label="Questions from the run">
            {prompts.map((prompt) => (
                <PromptCard key={prompt.id} runId={runId} prompt={prompt} onAnswered={onAnswered} />
            ))}
        </section>
    )
}

function PromptCard({
    runId,
    prompt,
    onAnswered,
}: {
    runId: number
    prompt: RunPrompt
    onAnswered: (prompt: RunPrompt) => void
}) {
    const [value, setValue] = useState(prompt.default ?? '')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const submit = async () => {
        setBusy(true)
        setError(null)
        try {
            const { prompt: answered } = await runsApi.answerPrompt(runId, prompt.id, value)
            setValue('')
            onAnswered(answered)
        } catch (cause) {
            setError(errorMessage(cause, 'The answer was not sent.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <form
            className="run-prompt"
            onSubmit={(event) => {
                event.preventDefault()
                void submit()
            }}
        >
            <div className="run-prompt-heading">
                {prompt.secret ? <KeyRound size={16} aria-hidden="true" /> : <MessageSquareText size={16} aria-hidden="true" />}
                <span>
                    <strong>{prompt.label}</strong>
                    <small>
                        {prompt.step ? `${prompt.step} is waiting for your answer` : 'The run is waiting for your answer'}
                        {prompt.secret ? ' · secret, never shown or logged' : ''}
                    </small>
                </span>
            </div>
            {prompt.description && <p className="run-prompt-description">{prompt.description}</p>}
            <div className="run-prompt-row">
                {prompt.choices?.length ? (
                    <select value={value} onChange={(event) => setValue(event.target.value)} aria-label={prompt.label} autoFocus>
                        {!prompt.default && <option value="">Choose…</option>}
                        {prompt.choices.map((choice) => (
                            <option key={choice} value={choice}>
                                {choice}
                            </option>
                        ))}
                    </select>
                ) : (
                    <input
                        type={prompt.secret ? 'password' : 'text'}
                        autoComplete={prompt.secret ? 'new-password' : 'off'}
                        value={value}
                        onChange={(event) => setValue(event.target.value)}
                        aria-label={prompt.label}
                        placeholder={prompt.default ? `Default: ${prompt.default}` : 'Your answer'}
                        autoFocus
                    />
                )}
                <button
                    type="submit"
                    className="entropy-button entropy-button-primary"
                    disabled={busy || (Boolean(prompt.choices?.length) && !value)}
                >
                    {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Send size={15} />} Answer
                </button>
            </div>
            {error && (
                <p className="run-prompt-error" role="alert">
                    {error}
                </p>
            )}
        </form>
    )
}
