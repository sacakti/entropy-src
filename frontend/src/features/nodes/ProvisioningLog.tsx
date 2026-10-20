import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, LoaderCircle, XCircle } from 'lucide-react'

import { nodesApi, type ProvisioningRecord } from '../../api/runs.api'
import { errorMessage, formatTime } from '../runs/format'

const ICONS = {
    info: Circle,
    success: CheckCircle2,
    warning: AlertTriangle,
    error: XCircle,
} as const

/** Follows a node setup (or removal) until it finishes. */
export default function ProvisioningLog({
    id,
    onFinished,
}: {
    id: number
    onFinished?: (record: ProvisioningRecord) => void
}) {
    const [record, setRecord] = useState<ProvisioningRecord | null>(null)
    const [error, setError] = useState<string | null>(null)
    const listRef = useRef<HTMLOListElement>(null)
    const finished = useRef(onFinished)

    useEffect(() => {
        finished.current = onFinished
    })

    useEffect(() => {
        let active = true
        let timer: ReturnType<typeof setTimeout> | undefined

        const poll = async () => {
            try {
                const next = await nodesApi.provisioning(id)
                if (!active) return
                setRecord(next)
                setError(null)
                if (next.status === 'running') {
                    timer = setTimeout(() => void poll(), 1500)
                } else {
                    finished.current?.(next)
                }
            } catch (cause) {
                if (!active) return
                setError(errorMessage(cause, 'Unable to read setup progress.'))
                timer = setTimeout(() => void poll(), 4000)
            }
        }

        void poll()
        return () => {
            active = false
            if (timer) clearTimeout(timer)
        }
    }, [id])

    useEffect(() => {
        if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
    }, [record?.log.length])

    return (
        <div className="provision-log">
            <div className={`start-run-check is-${record?.status === 'succeeded' ? 'valid' : record?.status === 'failed' ? 'invalid' : 'checking'}`} role="status">
                {!record || record.status === 'running' ? (
                    <LoaderCircle size={16} className="entropy-spin" />
                ) : record.status === 'succeeded' ? (
                    <CheckCircle2 size={16} />
                ) : (
                    <XCircle size={16} />
                )}
                <span>
                    {!record || record.status === 'running'
                        ? record?.action === 'uninstall'
                            ? 'Removing the agent…'
                            : 'Setting up the node…'
                        : record.status === 'succeeded'
                          ? record.action === 'uninstall'
                              ? 'Agent removed.'
                              : 'Node ready.'
                          : 'Setup failed.'}
                </span>
            </div>
            {error && <p className="run-card-muted">{error}</p>}
            <ol ref={listRef} className="provision-steps" aria-live="polite">
                {record?.log.map((line, index) => {
                    const Icon = ICONS[line.level] ?? Circle
                    return (
                        <li key={index} className={`is-${line.level}`}>
                            <Icon size={14} aria-hidden="true" />
                            <span>{line.message}</span>
                            <time>{formatTime(line.at)}</time>
                        </li>
                    )
                })}
            </ol>
        </div>
    )
}
