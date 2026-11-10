import { useState } from 'react'
import { zonedClock } from '../../services/timezone'

/**
 * A small analog clock. The second hand sweeps on its own (a CSS animation started
 * at the current second), so it moves smoothly without redrawing every frame.
 */
export default function VisionClockFace({ now }: { now: Date }) {
    const clock = zonedClock(now)
    const seconds = clock.seconds + now.getMilliseconds() / 1000
    const minutes = clock.minutes + seconds / 60
    const hours = (clock.hours % 12) + minutes / 60
    // Fixed once per mount: the animation keeps time from there.
    const [sweepDelay] = useState(() => `-${seconds.toFixed(2)}s`)
    return (
        <svg className="vision-clock" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="vision-clock-face" cx="12" cy="12" r="10.5" />
            {[0, 90, 180, 270].map((angle) => (
                <line key={angle} className="vision-clock-tick" x1="12" y1="2.6" x2="12" y2="4.2" transform={`rotate(${angle} 12 12)`} />
            ))}
            <line className="vision-clock-hour" x1="12" y1="12" x2="12" y2="7" transform={`rotate(${hours * 30} 12 12)`} />
            <line className="vision-clock-minute" x1="12" y1="12" x2="12" y2="4.6" transform={`rotate(${minutes * 6} 12 12)`} />
            <g className="vision-clock-sweep" style={{ animationDelay: sweepDelay }}>
                <line className="vision-clock-second" x1="12" y1="14" x2="12" y2="3.6" />
            </g>
            <circle className="vision-clock-pin" cx="12" cy="12" r="1.3" />
        </svg>
    )
}
