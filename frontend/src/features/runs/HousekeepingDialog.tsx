import { useEffect, useState } from 'react'
import { Archive, LoaderCircle } from 'lucide-react'

import { runsApi, type ArchiveRules, type Housekeeping } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from './format'
import { useErrorToast } from '../../components/feedback/useToast'

/** Archive policy for finished runs and their events. */
export default function HousekeepingDialog({
    onClose,
    onApplied,
}: {
    onClose: () => void
    onApplied: () => void
}) {
    const { notify } = useFeedback()
    const [settings, setSettings] = useState<Housekeeping | null>(null)
    const [archiveAfter, setArchiveAfter] = useState('30')
    const [purgeAfter, setPurgeAfter] = useState('365')
    const [rules, setRules] = useState<ArchiveRules>({
        schedule: false,
        plugin: false,
        completed: false,
        failed: false,
        cancelled: false,
        workflows: [],
    })
    const [busy, setBusy] = useState<'save' | 'run' | null>(null)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)

    useEffect(() => {
        let active = true
        runsApi
            .housekeeping()
            .then((loaded) => {
                if (!active) return
                setSettings(loaded)
                setArchiveAfter(String(loaded.archive_after_days))
                setPurgeAfter(String(loaded.purge_archive_after_days))
                setRules(loaded.archive_rules)
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load housekeeping settings.'))
            })
        return () => {
            active = false
        }
    }, [])

    const apply = async (runNow: boolean) => {
        setBusy(runNow ? 'run' : 'save')
        setError(null)
        try {
            const result = await runsApi.updateHousekeeping({
                archive_after_days: Number(archiveAfter),
                purge_archive_after_days: Number(purgeAfter),
                archive_rules: rules,
                run_now: runNow,
            })
            setSettings(result)
            if (runNow && result.result) {
                notify.success(
                    `${result.result.archived_jobs} run${result.result.archived_jobs === 1 ? '' : 's'} archived, ` +
                        `${result.result.purged_jobs} purged from the archive.`,
                    { title: 'Housekeeping complete' },
                )
                onApplied()
            } else {
                notify.success('Housekeeping policy saved.')
            }
            onClose()
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to save housekeeping settings.'))
        } finally {
            setBusy(null)
        }
    }

    return (
        <Dialog
            title="Housekeeping"
            subtitle="Archive finished runs by age or rule. Housekeeping runs automatically every hour."
            icon={<Archive size={18} />}
            onClose={onClose}
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => void apply(true)}
                        disabled={busy !== null || !settings}
                    >
                        {busy === 'run' && <LoaderCircle size={15} className="entropy-spin" />}
                        Save and run now
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => void apply(false)}
                        disabled={busy !== null || !settings}
                    >
                        {busy === 'save' && <LoaderCircle size={15} className="entropy-spin" />}
                        Save
                    </button>
                </>
            }
        >
            <div className="admin-form-grid">
                <label className="admin-field">
                    <span>Archive finished runs after (days)</span>
                    <input
                        type="number"
                        min={1}
                        max={3650}
                        value={archiveAfter}
                        onChange={(event) => setArchiveAfter(event.target.value)}
                    />
                    <small>Completed, failed and cancelled runs older than this leave the Runs list.</small>
                </label>
                <label className="admin-field">
                    <span>Delete archived runs after (days)</span>
                    <input
                        type="number"
                        min={0}
                        max={36500}
                        value={purgeAfter}
                        onChange={(event) => setPurgeAfter(event.target.value)}
                    />
                    <small>0 keeps the archive forever.</small>
                </label>
            </div>
            <div className="runs-archive-toggles">
                {([
                    ['schedule', 'Archive runs triggered by a schedule'],
                    ['plugin', 'Archive plugin runs'],
                    ['completed', 'Always archive completed runs'],
                    ['failed', 'Always archive failed runs'],
                    ['cancelled', 'Always archive cancelled runs'],
                ] as const).map(([key, label]) => (
                    <label className="admin-field admin-field-checkbox" key={key}>
                        <input
                            type="checkbox"
                            checked={rules[key]}
                            onChange={(event) => setRules({ ...rules, [key]: event.target.checked })}
                        />
                        <span>{label}</span>
                    </label>
                ))}
            </div>
            <div className="admin-field">
                <span>Archive matching workflows</span>
                {rules.workflows.map((rule, index) => (
                    <div className="runs-archive-rule" key={`${index}-${rule.pattern}`}>
                        <select className="entropy-select" value={rule.mode} aria-label="Workflow match type" onChange={(event) => {
                            const workflows = [...rules.workflows]
                            workflows[index] = { ...rule, mode: event.target.value as 'exact' | 'startswith' }
                            setRules({ ...rules, workflows })
                        }}>
                            <option value="exact">Matches</option>
                            <option value="startswith">Starts with</option>
                        </select>
                        <input value={rule.pattern} maxLength={200} aria-label="Workflow name" placeholder="Workflow name or prefix" onChange={(event) => {
                            const workflows = [...rules.workflows]
                            workflows[index] = { ...rule, pattern: event.target.value }
                            setRules({ ...rules, workflows })
                        }} />
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={() => setRules({ ...rules, workflows: rules.workflows.filter((_, i) => i !== index) })}>Remove</button>
                    </div>
                ))}
                <button type="button" className="entropy-button entropy-button-secondary" disabled={rules.workflows.length >= 100} onClick={() => setRules({ ...rules, workflows: [...rules.workflows, { mode: 'exact', pattern: '' }] })}>Add workflow rule</button>
                <small>Matching is case-insensitive. Rule-based archival applies to finished runs during hourly housekeeping.</small>
            </div>
            {settings && (
                <p className="runs-dialog-note">
                    The archive holds {settings.archived.jobs} run{settings.archived.jobs === 1 ? '' : 's'} and{' '}
                    {settings.archived.events} event{settings.archived.events === 1 ? '' : 's'}.
                </p>
            )}
        </Dialog>
    )
}
