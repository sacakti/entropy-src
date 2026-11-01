import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'

import type { SortState } from './useSort'

/** A sortable column heading (put it inside the <th>). */
export default function SortHeader<F extends string>({ label, field, sort, onSort }: {
    label: string
    field: F
    sort: SortState<F>
    onSort: (field: F) => void
}) {
    const active = sort.field === field
    return (
        <button type="button" className="list-sort" onClick={() => onSort(field)} aria-label={`Sort by ${label}`} aria-pressed={active}>
            {label}
            {active ? sort.order === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} /> : <ArrowUpDown size={14} />}
        </button>
    )
}
