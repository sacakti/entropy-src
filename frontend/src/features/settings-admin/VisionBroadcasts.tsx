import { useCallback, useEffect, useState } from 'react'
import { Megaphone, Send } from 'lucide-react'

import { visionApi, type BroadcastLevel, type VisionBroadcast } from '../../api/vision.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { localeString } from '../../services/timezone'

const MAX_MESSAGE = 500

const TEMPLATES: { label: string; message: string; level: BroadcastLevel; minutes: number }[] = [
    {
        label: 'Upgrade soon',
        message: 'Entropy will be upgraded in 15 minutes and be briefly unavailable. Please save your work.',
        level: 'warning',
        minutes: 60,
    },
    {
        label: 'Upgrade in progress',
        message: 'Entropy is being upgraded. It may be unavailable for a few minutes.',
        level: 'error',
        minutes: 60,
    },
    {
        label: 'Upgrade finished',
        message: 'The upgrade is finished. Please reload your page.',
        level: 'info',
        minutes: 60,
    },
]

const DURATIONS = [
    { minutes: 15, label: '15 minutes' },
    { minutes: 60, label: '1 hour' },
    { minutes: 240, label: '4 hours' },
    { minutes: 1440, label: '1 day' },
    { minutes: 0, label: 'Until ended' },
]

/** Send a message to everyone through Vision, and end ones that are still showing. */
export default function VisionBroadcasts({ enabled }: { enabled: boolean }) {
    const { notify, modal } = useFeedback()
    const [text, setText] = useState('')
    const [level, setLevel] = useState<BroadcastLevel>('info')
    const [minutes, setMinutes] = useState(60)
    const [active, setActive] = useState<VisionBroadcast[]>([])
    const [busy, setBusy] = useState(false)

    const load = useCallback(() => {
        visionApi
            .status()
            .then((status) => setActive(status.broadcasts))
            .catch(() => setActive([]))
    }, [])

    useEffect(() => {
        load()
    }, [load, enabled])

    const send = async () => {
        const trimmed = text.trim()
        if (!trimmed) return
        const confirmed = await modal.confirm({
            title: 'Send to everyone?',
            message: `Everyone using Entropy will see: “${trimmed}”`,
            confirmText: 'Send to everyone',
        })
        if (!confirmed) return
        setBusy(true)
        try {
            await visionApi.send({ message: trimmed, level, duration_minutes: minutes })
            setText('')
            load()
            notify.success('Message sent to everyone.')
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'The message was not sent.', { title: 'Not sent' })
        } finally {
            setBusy(false)
        }
    }

    const end = async (id: number) => {
        try {
            await visionApi.end(id)
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'The message was not ended.', { title: 'Not ended' })
        }
        load()
    }

    return (
        <section className="vision-broadcast">
            <h3><Megaphone size={16} aria-hidden="true" /> Message everyone</h3>
            <p className="vision-broadcast-hint">
                Shown in Vision to everyone using Entropy, and to anyone who signs in while it is active, until they dismiss it.
            </p>
            {!enabled && (
                <p className="vision-broadcast-hint">Turn Vision on and save to send a message.</p>
            )}

            <div className="vision-broadcast-templates" role="group" aria-label="Message templates">
                {TEMPLATES.map((template) => (
                    <button
                        key={template.label}
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        disabled={!enabled}
                        onClick={() => {
                            setText(template.message)
                            setLevel(template.level)
                            setMinutes(template.minutes)
                        }}
                    >
                        {template.label}
                    </button>
                ))}
            </div>

            <div className="settings-grid">
                <label className="admin-field admin-field-wide">
                    <span>Message</span>
                    <textarea
                        rows={3}
                        value={text}
                        maxLength={MAX_MESSAGE}
                        disabled={!enabled}
                        placeholder="Write your own message, or start from a template."
                        onChange={(event) => setText(event.target.value)}
                    />
                    <small>{text.length} of {MAX_MESSAGE}</small>
                </label>
                <label className="admin-field">
                    <span>Level</span>
                    <select className="entropy-select" value={level} disabled={!enabled} onChange={(event) => setLevel(event.target.value as BroadcastLevel)}>
                        <option value="info">Information</option>
                        <option value="warning">Warning</option>
                        <option value="error">Urgent</option>
                    </select>
                </label>
                <label className="admin-field">
                    <span>Show for</span>
                    <select className="entropy-select" value={minutes} disabled={!enabled} onChange={(event) => setMinutes(Number(event.target.value))}>
                        {DURATIONS.map((item) => (
                            <option key={item.minutes} value={item.minutes}>{item.label}</option>
                        ))}
                    </select>
                </label>
            </div>

            <div>
                <button
                    type="button"
                    className="entropy-button entropy-button-primary"
                    disabled={!enabled || busy || !text.trim()}
                    onClick={() => void send()}
                >
                    <Send size={15} aria-hidden="true" /> Send to everyone
                </button>
            </div>

            {active.length > 0 && (
                <>
                    <h3>Showing now</h3>
                    <ul className="vision-broadcast-list">
                        {active.map((item) => (
                            <li key={item.id}>
                                <div>
                                    <strong>{item.message}</strong>
                                    <small>
                                        Sent by {item.created_by}
                                        {item.expires_at ? ` · until ${localeString(item.expires_at)}` : ' · until ended'}
                                    </small>
                                </div>
                                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void end(item.id)}>
                                    End
                                </button>
                            </li>
                        ))}
                    </ul>
                </>
            )}
        </section>
    )
}
