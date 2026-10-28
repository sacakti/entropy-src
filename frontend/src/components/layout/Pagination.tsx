import { ChevronLeft, ChevronRight } from 'lucide-react'

import { PAGE_SIZES, type PaginationState } from './usePagination'

/** Footer for a paginated list: range, page size, page picker and arrows. */
export default function Pagination<T>({ state, noun }: { state: PaginationState<T>; noun: string }) {
    const { page, pages, pageSize, total, setPage, setPageSize } = state
    if (!total) return null
    const first = (page - 1) * pageSize + 1
    const last = Math.min(page * pageSize, total)

    return (
        <footer className="list-pagination">
            <span className="list-pagination-summary">
                Showing {first}–{last} of {total} {noun}
            </span>
            <div className="list-pagination-controls">
                <label>
                    Per page{' '}
                    <select className="entropy-select list-page-select" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))} aria-label={`${noun} per page`}>
                        {PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
                    </select>
                </label>
                <label>
                    Page{' '}
                    <select className="entropy-select list-page-select" value={page} onChange={(event) => setPage(Number(event.target.value))} disabled={pages <= 1} aria-label="Page">
                        {Array.from({ length: pages }, (_, index) => index + 1).map((number) => <option key={number} value={number}>{number}</option>)}
                    </select>
                </label>
                <span>of {pages}</span>
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                    <ChevronLeft size={17} />
                </button>
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                    <ChevronRight size={17} />
                </button>
            </div>
        </footer>
    )
}
