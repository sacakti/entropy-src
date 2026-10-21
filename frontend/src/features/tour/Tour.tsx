import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Sparkles, X } from 'lucide-react'

import AppPortal from '../../components/layout/AppPortal'
import '../../styles/tour.css'

export interface TourStep {
    /** `data-tour` name of the element to point at; none centres the card. */
    target?: string
    title: string
    body: string
}

interface Box {
    top: number
    left: number
    width: number
    height: number
}

const PAD = 6
const GAP = 12
const CARD_WIDTH = 340
const MARGIN = 16

function find(target?: string): HTMLElement | null {
    if (!target) return null
    const element = document.querySelector<HTMLElement>(`[data-tour="${target}"]`)
    if (!element) return null
    const rect = element.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0 ? element : null
}

/** Card position next to the highlighted box, kept inside the window. */
function place(box: Box | null, card: { width: number; height: number }) {
    const vw = window.innerWidth
    const vh = window.innerHeight
    const width = Math.min(card.width, vw - MARGIN * 2)
    if (!box) {
        return { top: Math.max(MARGIN, (vh - card.height) / 2), left: (vw - width) / 2, width }
    }
    const clampLeft = (left: number) => Math.min(Math.max(MARGIN, left), vw - width - MARGIN)
    const clampTop = (top: number) => Math.min(Math.max(MARGIN, top), vh - card.height - MARGIN)
    // Below, then above, then to the right (tall targets such as the sidebar).
    if (box.top + box.height + GAP + card.height <= vh - MARGIN && box.height < vh / 2) {
        return { top: box.top + box.height + GAP, left: clampLeft(box.left + box.width - width), width }
    }
    if (box.top - GAP - card.height >= MARGIN && box.height < vh / 2) {
        return { top: box.top - GAP - card.height, left: clampLeft(box.left + box.width - width), width }
    }
    if (box.left + box.width + GAP + width <= vw - MARGIN) {
        return { top: clampTop(box.top + 24), left: box.left + box.width + GAP, width }
    }
    return { top: clampTop(vh - card.height - MARGIN), left: clampLeft((vw - width) / 2), width }
}

/**
 * A short guided tour: dims the page, highlights one part of it at a time
 * and explains it. Steps whose element is not on screen are skipped.
 */
export default function Tour({ steps, onFinish }: { steps: TourStep[]; onFinish: () => void }) {
    const visible = useMemo(() => steps.filter((step) => !step.target || find(step.target)), [steps])
    const [index, setIndex] = useState(0)
    const [box, setBox] = useState<Box | null>(null)
    const [cardSize, setCardSize] = useState({ width: CARD_WIDTH, height: 200 })
    const cardRef = useRef<HTMLDivElement>(null)
    const step = visible[index]
    const last = index === visible.length - 1

    const measure = useCallback(() => {
        const element = find(step?.target)
        if (!element) {
            setBox(null)
            return
        }
        const rect = element.getBoundingClientRect()
        setBox({
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
        })
    }, [step])

    useLayoutEffect(() => {
        find(step?.target)?.scrollIntoView({ block: 'nearest' })
        const frame = requestAnimationFrame(measure)
        return () => cancelAnimationFrame(frame)
    }, [measure, step])

    useLayoutEffect(() => {
        const frame = requestAnimationFrame(() => {
            const card = cardRef.current
            if (card) setCardSize({ width: CARD_WIDTH, height: card.offsetHeight })
        })
        return () => cancelAnimationFrame(frame)
    }, [index, box])

    useEffect(() => {
        window.addEventListener('resize', measure)
        window.addEventListener('scroll', measure, true)
        return () => {
            window.removeEventListener('resize', measure)
            window.removeEventListener('scroll', measure, true)
        }
    }, [measure])

    useEffect(() => {
        cardRef.current?.focus()
    }, [index])

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation()
                onFinish()
            } else if (event.key === 'ArrowRight') {
                if (last) onFinish()
                else setIndex((value) => value + 1)
            } else if (event.key === 'ArrowLeft') {
                setIndex((value) => Math.max(0, value - 1))
            }
        }
        document.addEventListener('keydown', onKey, true)
        return () => document.removeEventListener('keydown', onKey, true)
    }, [last, onFinish])

    if (!step) return null
    const position = place(box, cardSize)

    return (
        <AppPortal>
            <div className="tour-layer">
                {box ? (
                    <div
                        className="tour-spotlight"
                        style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
                    />
                ) : (
                    <div className="tour-dim" />
                )}
                <div
                    ref={cardRef}
                    className="tour-card"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="tour-title"
                    aria-describedby="tour-body"
                    tabIndex={-1}
                    style={{ top: position.top, left: position.left, width: position.width }}
                >
                    <header>
                        <span className="tour-icon" aria-hidden="true">
                            <Sparkles size={16} />
                        </span>
                        <h2 id="tour-title">{step.title}</h2>
                        <button type="button" className="tour-close" aria-label="Skip the tour" onClick={onFinish}>
                            <X size={16} />
                        </button>
                    </header>
                    <p id="tour-body">{step.body}</p>
                    <footer>
                        <span className="tour-progress" aria-label={`Step ${index + 1} of ${visible.length}`}>
                            {visible.map((item, at) => (
                                <i key={item.title} className={at === index ? 'is-active' : undefined} />
                            ))}
                        </span>
                        {index === 0 ? (
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={onFinish}>
                                Skip
                            </button>
                        ) : (
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={() => setIndex((value) => value - 1)}
                            >
                                <ArrowLeft size={14} /> Back
                            </button>
                        )}
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-sm"
                            onClick={() => (last ? onFinish() : setIndex((value) => value + 1))}
                        >
                            {last ? 'Get started' : (
                                <>
                                    Next <ArrowRight size={14} />
                                </>
                            )}
                        </button>
                    </footer>
                </div>
            </div>
        </AppPortal>
    )
}
