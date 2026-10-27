import { useState } from 'react'
import { LoaderCircle, Trash2 } from 'lucide-react'

import { runsApi } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { errorMessage } from './format'
import { useErrorToast } from '../../components/feedback/useToast'

export default function PurgeArchiveDialog({
    archivedJobs,
    onClose,
    onPurged,
}: {
    archivedJobs: number
    onClose: () => void
    onPurged: () => void
}) {
    const { notify } = useFeedback()
    const [days, setDays] = useState('30')
    const [purgeAll, setPurgeAll] = useState(false)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)

    const selection = purgeAll ? { purge_all: true } : { older_than_days: Number(days) }

    const purge = async (downloadFirst: boolean) => {
        setBusy(true)
        setError(null)
        try {
            if (downloadFirst) await runsApi.exportArchive(selection)
            const result = await runsApi.purgeArchive(selection)
            notify.success(
                `${result.purged_jobs} archived run${result.purged_jobs === 1 ? '' : 's'} ` +
                    (downloadFirst ? 'downloaded and purged.' : 'purged.'),
                {
                    title: downloadFirst ? 'Archive downloaded and purged' : 'Archive purged',
                },
            )
            onPurged()
            onClose()
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to purge archived runs.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title="Purge archived runs"
            subtitle={`${archivedJobs} archived run${archivedJobs === 1 ? '' : 's'} currently stored.`}
            icon={<Trash2 size={18} />}
            onClose={onClose}
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-danger-quiet"
                        onClick={() => void purge(false)}
                        disabled={busy || (!purgeAll && (!Number.isInteger(Number(days)) || Number(days) < 1))}
                    >
                        Purge only
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-danger"
                        onClick={() => void purge(true)}
                        disabled={busy || (!purgeAll && (!Number.isInteger(Number(days)) || Number(days) < 1))}
                    >
                        {busy && <LoaderCircle size={15} className="entropy-spin" />}
                        Download .tar.gz & purge
                    </button>
                </>
            }
        >
            <div className="admin-form-grid">
                <label className="admin-field">
                    <span>Purge archived runs older than (days)</span>
                    <input
                        type="number"
                        min={1}
                        max={36500}
                        value={days}
                        disabled={purgeAll}
                        onChange={(event) => setDays(event.target.value)}
                    />
                    <small>The download and purge will both use this age cutoff.</small>
                </label>
            </div>
            <label className="admin-field admin-field-checkbox runs-purge-all">
                <input type="checkbox" checked={purgeAll} onChange={(event) => setPurgeAll(event.target.checked)} />
                <span>Purge all archived runs now</span>
            </label>
            {purgeAll && (
                <p className="runs-dialog-note">
                    The download includes every archived run. The purge permanently deletes those runs and their saved events.
                </p>
            )}
        </Dialog>
    )
}
