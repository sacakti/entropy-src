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

    useEffect(() => {
        let active = true
        alertsApi
            .get(kind, target)
            .then((result) => {
                if (!active) return
                setValues(result)
                setEmails(result.emails.join(', '))
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
