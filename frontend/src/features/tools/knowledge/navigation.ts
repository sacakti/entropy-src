/** Entry id named by a hash such as `#/tools/knowledge?entry=7`, if any. */
export function entryIdFromHash(hash: string): number | null {
    const match = /^#\/?tools\/knowledge\?(?:.*&)?entry=(\d+)/.exec(hash)
    return match ? Number(match[1]) : null
}

/** Open a knowledge base entry, from anywhere (a history entry, so Back returns). */
export function openKnowledgeEntry(id: number): void {
    window.history.pushState(null, '', `#/tools/knowledge?entry=${id}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
}
