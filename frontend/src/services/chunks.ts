/** Split ids for an endpoint that takes at most `size` per request. */
export function inChunks<T>(items: readonly T[], size: number): T[][] {
    const chunks: T[][] = []
    for (let start = 0; start < items.length; start += size) chunks.push(items.slice(start, start + size))
    return chunks
}
