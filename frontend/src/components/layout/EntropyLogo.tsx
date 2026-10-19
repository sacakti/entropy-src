/**
 * Entropy mark drawn with the active theme's accent tokens, so it follows the
 * user's theme and accent preference (the static /entropy-logo.svg cannot).
 */
export default function EntropyLogo({
    size = 38,
    className,
    title = 'Entropy',
}: {
    size?: number
    className?: string
    title?: string
}) {
    return (
        <svg
            className={['entropy-logo-mark', className].filter(Boolean).join(' ')}
            width={size}
            height={size}
            viewBox="0 0 64 64"
            role="img"
            aria-label={title}
        >
            <rect
                className="entropy-logo-mark-tile"
                x="1.5"
                y="1.5"
                width="61"
                height="61"
                rx="15"
                strokeWidth="2"
            />
            <g
                className="entropy-logo-mark-glyph"
                fill="none"
                strokeWidth="3.6"
                strokeLinecap="round"
                strokeLinejoin="round"
            >
                <rect x="19" y="17" width="12" height="12" rx="3" />
                <path d="M31 23h6a4 4 0 0 1 4 4v6" />
                <rect x="35" y="33" width="12" height="12" rx="3" />
                <path d="M29 29v7a4 4 0 0 0 4 4h2" />
            </g>
        </svg>
    )
}
