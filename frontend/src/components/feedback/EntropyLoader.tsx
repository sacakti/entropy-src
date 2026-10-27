/**
 * The Entropy loader: the Entropy mark with its two blocks trading places.
 * Use it wherever something is loading instead of plain "Loading…" text;
 * `label` stays available to screen readers and is shown under the mark.
 */
export default function EntropyLoader({
    label = 'Loading…',
    size = 40,
    inline = false,
    className,
}: {
    label?: string
    size?: number
    /** A small mark and label on one line (inside lists, buttons, rows). */
    inline?: boolean
    className?: string
}) {
    return (
        <div
            className={['entropy-loader', inline ? 'is-inline' : '', className].filter(Boolean).join(' ')}
            role="status"
            aria-live="polite"
        >
            <svg className="entropy-loader-mark" width={inline ? 18 : size} height={inline ? 18 : size} viewBox="0 0 64 64" aria-hidden="true">
                <rect className="entropy-logo-mark-tile" x="1.5" y="1.5" width="61" height="61" rx="15" strokeWidth="2" />
                <g className="entropy-logo-mark-glyph" fill="none" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
                    <rect className="entropy-loader-block entropy-loader-block-a" x="19" y="17" width="12" height="12" rx="3" />
                    <path className="entropy-loader-link" d="M31 23h6a4 4 0 0 1 4 4v6" />
                    <rect className="entropy-loader-block entropy-loader-block-b" x="35" y="33" width="12" height="12" rx="3" />
                    <path className="entropy-loader-link" d="M29 29v7a4 4 0 0 0 4 4h2" />
                </g>
            </svg>
            {label && <span className="entropy-loader-label">{label}</span>}
        </div>
    )
}
