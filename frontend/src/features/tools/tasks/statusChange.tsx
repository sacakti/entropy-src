import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { statusTitle, type Status, type Task } from './model'

export type StatusUpdate = { status: Status; reason?: string }

/** Checks a status move; reopening a closed task asks for the reason. */
export function useStatusChange() {
    const { modal, notify } = useFeedback()

    return async (task: Task, status: Status): Promise<StatusUpdate | null> => {
        if (task.status === status) return null
        if (task.status === 'done' && status !== 'reopened') {
            notify.warning(`${task.key} is closed. Reopen it, with a reason, to work on it again.`, { title: 'Closed tasks stay closed' })
            return null
        }
        if (status === 'reopened' && task.status !== 'done') {
            notify.warning(`Only a closed task can be reopened; ${task.key} is ${statusTitle(task.status).toLowerCase()}.`, { title: 'Not closed' })
            return null
        }
        if (status !== 'reopened') return { status }
        let reason = ''
        const confirmed = await modal.confirm({
            title: `Reopen ${task.key}?`,
            confirmText: 'Reopen',
            cancelText: 'Cancel',
            content: (
                <label className="task-reopen">
                    <span>Why does “{task.title}” need more work? The reason is kept in the task's history and sent to its followers.</span>
                    <textarea autoFocus rows={3} maxLength={2000} onChange={(event) => (reason = event.target.value)} />
                </label>
            ),
        })
        if (!confirmed) return null
        if (!reason.trim()) {
            notify.warning('Give a reason to reopen the task.', { title: 'Reason needed' })
            return null
        }
        return { status, reason: reason.trim() }
    }
}
