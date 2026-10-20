import type { RunTab } from '../../api/runs.api'

/** Run id named by a hash such as `#/runs/42`, if any. */
export function runIdFromHash(hash: string): number | null {
    const match = /^#\/?runs\/(\d+)$/.exec(hash)
    return match ? Number(match[1]) : null
}

/** Show the live screen of a run (a history entry, so Back returns). */
export function openRun(id: number): void {
    window.history.pushState(null, '', `#/runs/${id}`)
    // The shell follows the hash through popstate.
    window.dispatchEvent(new PopStateEvent('popstate'))
}

const RUN_TABS: readonly RunTab[] = ['active', 'completed', 'failed', 'cancelled', 'all']

/** Runs tab named by a hash such as `#/runs?tab=failed`, if any. */
export function runsTabFromHash(hash: string): RunTab | null {
    const match = /^#\/?runs\?(?:.*&)?tab=([a-z]+)/.exec(hash)
    const tab = match?.[1] as RunTab | undefined
    return tab && RUN_TABS.includes(tab) ? tab : null
}

/** Open the Runs page on a tab (a history entry, so Back returns). */
export function openRunsTab(tab: RunTab): void {
    window.history.pushState(null, '', `#/runs?tab=${tab}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
}
