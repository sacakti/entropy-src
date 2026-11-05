/** Whether a hash such as `#/tools/clash?mode=database` names the database compare. */
export function isDatabaseCompareHash(hash: string): boolean {
    return /^#\/?tools\/clash\?(?:.*&)?mode=database\b/.test(hash)
}

/** Open the database compare, from anywhere (a history entry, so Back returns). */
export function openDatabaseCompare(): void {
    window.history.pushState(null, '', '#/tools/clash?mode=database')
    // The shell and Clash follow the hash through popstate.
    window.dispatchEvent(new PopStateEvent('popstate'))
}
