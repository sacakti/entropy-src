import { useMemo, useState } from 'react'

export const PAGE_SIZES = [10, 25, 50, 100, 200]
const DEFAULT_PAGE_SIZE = 25

function storedSize(key: string): number {
    try {
        const value = Number(window.localStorage.getItem(`entropy.pageSize.${key}`))
        return PAGE_SIZES.includes(value) ? value : DEFAULT_PAGE_SIZE
    } catch {
        return DEFAULT_PAGE_SIZE
    }
}

export type PaginationState<T> = {
    page: number
    pages: number
    pageSize: number
    total: number
    pageItems: T[]
    setPage: (page: number) => void
    setPageSize: (size: number) => void
}

/**
 * Client-side pages of an already filtered list. The page size is kept per
 * list (`key`) in this browser; the page is clamped when the list shrinks.
 */
export function usePagination<T>(items: T[], key: string): PaginationState<T> {
    const [pageSize, setStoredSize] = usePageSize(key)
    const [requested, setPage] = useState(1)
    const pages = Math.max(1, Math.ceil(items.length / pageSize))
    const page = Math.min(Math.max(1, requested), pages)
    const pageItems = useMemo(() => items.slice((page - 1) * pageSize, page * pageSize), [items, page, pageSize])

    const setPageSize = (size: number) => {
        setStoredSize(size)
        setPage(1)
    }

    return { page, pages, pageSize, total: items.length, pageItems, setPage, setPageSize }
}

/** The page size of a list (`key`), remembered in this browser; for server-paged lists too. */
export function usePageSize(key: string): [number, (size: number) => void] {
    const [pageSize, setSize] = useState(() => storedSize(key))
    const update = (size: number) => {
        setSize(size)
        try {
            window.localStorage.setItem(`entropy.pageSize.${key}`, String(size))
        } catch {
            // Storage may be unavailable (private mode); the size still applies now.
        }
    }
    return [pageSize, update]
}
