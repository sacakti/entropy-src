import { Ban, CheckCircle2, CircleDashed, LoaderCircle, PauseCircle, XCircle } from 'lucide-react'

import type { RunState } from '../../api/runs.api'
import { STATE_LABELS } from './format'

const ICONS = {
    queued: CircleDashed,
    starting: LoaderCircle,
    running: LoaderCircle,
    paused: PauseCircle,
    completed: CheckCircle2,
    failed: XCircle,
    cancelled: Ban,
} as const

export default function RunStatus({ state }: { state: RunState }) {
    const Icon = ICONS[state] ?? CircleDashed
    const spinning = state === 'running' || state === 'starting'

    return (
        <span className={`run-status is-${state}`}>
            <Icon size={13} className={spinning ? 'entropy-spin' : undefined} aria-hidden="true" />
            {STATE_LABELS[state] ?? state}
        </span>
    )
}
