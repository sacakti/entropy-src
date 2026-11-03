/** Task id named by a hash such as `#/tools/tasks?task=42`, if any. */
export function taskIdFromHash(hash: string): number | null {
    const match = /^#\/?tools\/tasks\?(?:.*&)?task=(\d+)/.exec(hash)
    return match ? Number(match[1]) : null
}

/** Open a task, from anywhere (a history entry, so Back returns). */
export function openTask(id: number): void {
    window.history.pushState(null, '', `#/tools/tasks?task=${id}`)
    // The shell and the Tasks tool follow the hash through popstate.
    window.dispatchEvent(new PopStateEvent('popstate'))
}
