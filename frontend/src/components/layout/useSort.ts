import { useMemo, useState } from 'react'

export type SortOrder = 'asc' | 'desc'
export type SortState<F extends string> = { field: F; order: SortOrder }
export type Comparators<F extends string, T> = Record<F, (left: T, right: T) => number>

/** Text compare that reads numbers as numbers (1.10 after 1.9) and ignores case. */
export const compareText = (left: string | null | undefined, right: string | null | undefined) =>
    (left ?? '').localeCompare(right ?? '', undefined, { numeric: true, sensitivity: 'base' })

/** Dates/ISO strings or numbers; empty values sort first. */
export const compareValue = (left: string | number | null | undefined, right: string | number | null | undefined) => {
    if (left === right) return 0
    if (left === null || left === undefined || left === '') return -1
    if (right === null || right === undefined || right === '') return 1
    return left < right ? -1 : 1
}

function stored<F extends string>(key: string, fields: F[], fallback: SortState<F>): SortState<F> {
    try {
        const value = JSON.parse(window.localStorage.getItem(`entropy.sort.${key}`) ?? 'null') as SortState<F> | null
        if (value && fields.includes(value.field) && (value.order === 'asc' || value.order === 'desc')) return value
    } catch {
        // Storage may be unavailable or hold something else; use the default.
    }
    return fallback
}

/**
 * The sort of a list, kept per list (`key`) in this browser. Clicking the
 * active column reverses it; a new column starts ascending, or descending
 * for the fields in `descendingFirst` (dates: newest first).
 */
export function useSortState<F extends string>(key: string, fields: F[], initial: SortState<F>, descendingFirst: F[] = []) {
    const [sort, setSort] = useState<SortState<F>>(() => stored(key, fields, initial))
    const toggle = (field: F) => {
        const next: SortState<F> = sort.field === field
            ? { field, order: sort.order === 'asc' ? 'desc' : 'asc' }
            : { field, order: descendingFirst.includes(field) ? 'desc' : 'asc' }
        setSort(next)
        try {
            window.localStorage.setItem(`entropy.sort.${key}`, JSON.stringify(next))
        } catch {
            // The order still applies now.
        }
        return next
    }
    const ariaSort = (field: F): 'ascending' | 'descending' | undefined =>
        sort.field === field ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined
    return { sort, toggle, ariaSort }
}

/** Sorts a client-side list with per-column comparators. */
// NoInfer: the fields come from the comparators, not from the default sort.
export function useSort<F extends string, T>(items: T[], key: string, comparators: Comparators<F, T>, initial: SortState<NoInfer<F>>, descendingFirst: NoInfer<F>[] = []) {
    const state = useSortState(key, Object.keys(comparators) as F[], initial, descendingFirst)
    const { field, order } = state.sort
    const sorted = useMemo(() => {
        const compare = comparators[field]
        return [...items].sort((left, right) => (order === 'asc' ? compare(left, right) : compare(right, left)))
        // Comparators are module constants or stable per render.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [items, field, order])
    return { ...state, sorted }
}
