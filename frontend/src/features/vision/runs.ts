import type { Run } from '../../api/runs.api'

export type RunsLevel = 'waiting' | 'running' | 'waiting-others' | 'others' | 'idle'

export interface RunsSummary {
    /** The person's own runs; those waiting on them first. */
    mine: Run[]
    /** Others' runs in the project (none when the project shows only one's own); waiting first. */
    others: Run[]
    level: RunsLevel
    label: string
    /** The run a click should open, when the label names one that needs someone. */
    open: number | null
}

function waitingFirst(runs: Run[]): Run[] {
    return [...runs.filter((run) => run.waiting_for_input), ...runs.filter((run) => !run.waiting_for_input)]
}

function isMine(run: Run, username: string): boolean {
    return (run.username ?? '').toLowerCase() === username.toLowerCase()
}

const nameOf = (run: Run) => run.target || run.workflow
const ownerOf = (run: Run) => run.username || 'someone'

/**
 * What Vision says about the project's active runs. Own runs come first: what waits on
 * this person, then what they run, then others' (only if the project shares its activity).
 */
export function summarizeRuns(runs: Run[], username: string, projectActivity: boolean): RunsSummary {
    const mine = waitingFirst(runs.filter((run) => isMine(run, username)))
    const others = projectActivity ? waitingFirst(runs.filter((run) => !isMine(run, username))) : []
    const mineWaiting = mine.filter((run) => run.waiting_for_input)
    const othersWaiting = others.filter((run) => run.waiting_for_input)
    const summary = { mine, others }

    if (mineWaiting.length === 1) {
        const [run] = mineWaiting
        return { ...summary, level: 'waiting', label: `Run #${run.id} waiting for you: ${nameOf(run)}`, open: run.id }
    }
    if (mineWaiting.length > 1) {
        return { ...summary, level: 'waiting', label: `${mineWaiting.length} of your runs are waiting for you`, open: null }
    }
    if (mine.length) {
        const label = mine.length === 1 ? `Your run #${mine[0].id}: ${nameOf(mine[0])}` : `${mine.length} of your runs are running`
        const more = others.length ? ` · ${others.length} more in this project` : ''
        return { ...summary, level: 'running', label: label + more, open: null }
    }
    if (othersWaiting.length === 1) {
        const [run] = othersWaiting
        return {
            ...summary,
            level: 'waiting-others',
            label: `Run #${run.id} waiting for ${ownerOf(run)}: ${nameOf(run)}`,
            open: run.id,
        }
    }
    if (othersWaiting.length > 1) {
        return { ...summary, level: 'waiting-others', label: `${othersWaiting.length} runs waiting for others`, open: null }
    }
    if (others.length === 1) {
        const [run] = others
        return { ...summary, level: 'others', label: `${ownerOf(run)}'s run #${run.id}: ${nameOf(run)}`, open: null }
    }
    if (others.length > 1) {
        return { ...summary, level: 'others', label: `${others.length} running in this project`, open: null }
    }
    return { ...summary, level: 'idle', label: '', open: null }
}
