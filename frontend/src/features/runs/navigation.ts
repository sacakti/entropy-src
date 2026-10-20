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
