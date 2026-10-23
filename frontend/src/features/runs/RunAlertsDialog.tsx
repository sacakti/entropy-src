import { useEffect, useState } from 'react'
import { AlertCircle, BellRing, LoaderCircle } from 'lucide-react'

import { alertsApi, type RunAlertSettings } from '../../api/settings.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from './format'

const OUTCOMES: { key: 'on_success' | 'on_failure' | 'on_cancel'; label: string }[] = [
    { key: 'on_success', label: 'Completed' },
    { key: 'on_failure', label: 'Failed' },
    { key: 'on_cancel', label: 'Cancelled' },
]

const SAMPLES = {
    status: {
        subject: '[Entropy] {title} (run #{run_id})',
        body: '{message}\n\nProject: {project}\nStarted by: {started_by}\nSchedule: {schedule}\nNode: {node}\n\nOpen run: {run_url}',
    },
    complete: {
        subject: 'Job complete: {workflow} (run #{run_id})',
        body: 'The job completed successfully.\n\nWorkflow or plugin: {workflow}\nProject: {project}\nStarted by: {started_by}\nSchedule: {schedule}\nNode: {node}\n\nReview the run: {run_url}',
    },
    failure: {
        subject: 'Action required: {title} (run #{run_id})',
        body: 'A run needs attention.\n\nStatus: {status}\nWorkflow or plugin: {workflow}\nProject: {project}\nStarted by: {started_by}\nSchedule: {schedule}\nNode: {node}\n\nRecent output:\n{log}\n\nOpen the run: {run_url}',
    },
} as const

/**
 * E-mail alerts for a workflow's or a schedule's runs: who to write to and
 * for which outcomes. Without addresses, no e-mail is sent.
 */
export default function RunAlertsDialog({
    kind,
    target,
    name,
    canEdit,
    onClose,
}: {
    kind: 'workflow' | 'schedule'
    target: string | number
    name: string
    canEdit: boolean
    onClose: () => void
}) {
    const { notify } = useFeedback()
    const [values, setValues] = useState<RunAlertSettings | null>(null)
    const [emails, setEmails] = useState('')
    const [error, setError] = useState('')
    const [saving, setSaving] = useState(false)
    const [sample, setSample] = useState('')

    useEffect(() => {
        let active = true
        alertsApi
            .get(kind, target)
            .then((result) => {
                if (!active) return
                setValues(result)
                setEmails(result.emails.join(', '))
                setSample(result.subject_template || result.body_template ? 'custom' : '')
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load the alerts.'))
            })
        return () => {
            active = false
        }
    }, [kind, target])

    const addresses = emails
        .split(/[\s,;]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    const invalid = addresses.filter((item) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(item))

    const save = async () => {
        if (!values) return
        setSaving(true)
        setError('')
        try {
            await alertsApi.save(kind, target, { ...values, emails: addresses })
            notify.success(addresses.length ? `Alerts saved for ${name}.` : `Alerts turned off for ${name}.`)
            onClose()
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to save the alerts.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={`Alerts for ${name}`}
            subtitle={
                kind === 'workflow'
                    ? 'E-mail when any run of this workflow finishes: from the UI, a schedule or the command line.'
                    : "E-mail when this schedule's runs finish."
            }
            icon={<BellRing size={18} />}
            onClose={onClose}
            className="run-alerts-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        {canEdit ? 'Cancel' : 'Close'}
                    </button>
                    {canEdit && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            onClick={() => void save()}
                            disabled={!values || saving || invalid.length > 0}
                        >
                            {saving && <LoaderCircle size={15} className="entropy-spin" />}
                            Save
                        </button>
                    )}
                </>
            }
        >
            {!values && !error && (
                <div className="list-empty" role="status">
                    <LoaderCircle size={18} className="entropy-spin" /> Loading…
                </div>
            )}
            {values && (
                <div className="run-alerts">
                    {values.mail_ready === false && (
                        <p className="entropy-alert entropy-alert-warning" role="status">
                            <AlertCircle size={15} /> E-mail is not set up yet, so no alerts are sent. An
                            administrator sets it up in Administration → Settings → E-mail.
                        </p>
                    )}
                    <label className="admin-field">
                        <span>Send to</span>
                        <textarea
                            rows={3}
                            value={emails}
                            onChange={(event) => setEmails(event.target.value)}
                            placeholder="ops@example.com, oncall@example.com"
                            disabled={!canEdit}
                        />
                        <small>
                            {invalid.length
                                ? `Not an e-mail address: ${invalid.join(', ')}`
                                : 'Separate addresses with commas or new lines. Leave empty to send nothing.'}
                        </small>
                    </label>
                    <fieldset className="run-alerts-outcomes" disabled={!canEdit}>
                        <legend>When a run</legend>
                        {OUTCOMES.map(({ key, label }) => (
                            <label key={key}>
                                <input
                                    type="checkbox"
                                    checked={values[key]}
                                    onChange={(event) =>
                                        setValues((current) => (current ? { ...current, [key]: event.target.checked } : current))
                                    }
                                />
                                {label}
                            </label>
                        ))}
                    </fieldset>
                    <section className="run-alerts-template" aria-label="Email content">
                        <div className="run-alerts-template-heading">
                            <div><strong>Email content</strong><small>Choose a sample, then customize the subject and message.</small></div>
                            <select
                                className="entropy-select"
                                value={sample}
                                disabled={!canEdit}
                                aria-label="Sample email template"
                                onChange={(event) => {
                                    if (event.target.value === 'custom') return
                                    const key = event.target.value as keyof typeof SAMPLES
                                    setSample(event.target.value)
                                    setValues((current) => current ? {
                                        ...current,
                                        subject_template: key ? SAMPLES[key].subject : '',
                                        body_template: key ? SAMPLES[key].body : '',
                                    } : current)
                                }}
                            >
                                {sample === 'custom' && <option value="custom">Custom content</option>}
                                <option value="">Use Entropy default</option>
                                <option value="status">Rich status update</option>
                                <option value="complete">Job complete</option>
                                <option value="failure">Failure report</option>
                            </select>
                        </div>
                        <label className="admin-field">
                            <span>Subject</span>
                            <input maxLength={998} value={values.subject_template} disabled={!canEdit} onChange={(event) => setValues((current) => current ? { ...current, subject_template: event.target.value } : current)} placeholder="Leave blank for Entropy's default subject" />
                        </label>
                        <label className="admin-field">
                            <span>Message</span>
                            <textarea rows={7} maxLength={20000} value={values.body_template} disabled={!canEdit} onChange={(event) => setValues((current) => current ? { ...current, body_template: event.target.value } : current)} placeholder="Leave blank for Entropy's default message" />
                            <small>Available fields: {'{status}'}, {'{title}'}, {'{run_id}'}, {'{workflow}'}, {'{schedule}'}, {'{project}'}, {'{started_by}'}, {'{node}'}, {'{message}'}, {'{log}'}, {'{run_url}'}. Message text is placed in a styled HTML email and also sent as plain text.</small>
                        </label>
                    </section>
                    {values.updated_by && (
                        <p className="run-alerts-meta">
                            Last changed by {values.updated_by}
                            {values.updated_at ? ` on ${new Date(values.updated_at).toLocaleString()}` : ''}.
                        </p>
                    )}
                </div>
            )}
            {error && (
                <p className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={15} /> {error}
                </p>
            )}
        </Dialog>
    )
}
