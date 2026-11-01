import { useCallback, useEffect, useRef, useState } from 'react'
import { Clock, LoaderCircle, LogOut } from 'lucide-react'

import Dialog from '../layout/Dialog'
import { ApiError } from '../../services/api'
import { keepSessionAlive, sessionStatus, type SessionInfo } from '../../services/auth'

/** How long before the end the warning appears. */
const WARN_MS = 2 * 60 * 1000
/** Activity restarts the server's timer at most this often. */
const PING_MS = 60 * 1000
const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'pointermove'] as const

const clock = (ms: number) => {
    const seconds = Math.max(0, Math.ceil(ms / 1000))
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/**
 * Ends the browser session after the server's inactivity limit. Real use of
 * the page (pointer, keys, scrolling) restarts the server's timer; polling
 * does not. Two minutes before the end a dialog offers to continue.
 */
export default function SessionTimeout({ session, onExpired, onSignOut }: {
    session: SessionInfo
    /** The session ended for inactivity (or was ended elsewhere). */
    onExpired: () => void
    onSignOut: () => void
}) {
    const limit = session.idle_timeout_seconds * 1000
    const [deadline, setDeadline] = useState(() =>
        session.idle_expires_at ? new Date(session.idle_expires_at).getTime() : Date.now() + limit,
    )
    const [now, setNow] = useState(() => Date.now())
    const [warning, setWarning] = useState(false)
    const [busy, setBusy] = useState(false)
    const lastActivity = useRef(0)
    const lastPing = useRef(0)
    const checking = useRef(false)
    const warningRef = useRef(false)
    const expiredRef = useRef(onExpired)

    useEffect(() => {
        expiredRef.current = onExpired
        warningRef.current = warning
    }, [onExpired, warning])

    const apply = useCallback((info: SessionInfo) => {
        if (info.idle_expires_at) setDeadline(new Date(info.idle_expires_at).getTime())
    }, [])

    const failed = useCallback((cause: unknown) => {
        // 401: the session is gone (idle limit, sign-out elsewhere, restart).
        if (cause instanceof ApiError && cause.status === 401) expiredRef.current()
    }, [])

    const ping = useCallback(async () => {
        lastPing.current = Date.now()
        try {
            apply(await keepSessionAlive())
            return true
        } catch (cause) {
            failed(cause)
            return false
        }
    }, [apply, failed])

    // Real activity on the page (not while the warning asks for a decision).
    useEffect(() => {
        if (!limit) return
        const active = () => {
            if (!warningRef.current) lastActivity.current = Date.now()
        }
        // Opening or reloading the page is activity too: the first tick restarts the timer.
        lastActivity.current = Date.now()
        ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, active, { passive: true }))
        return () => ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, active))
    }, [limit])

    useEffect(() => {
        if (!limit) return
        const timer = window.setInterval(() => {
            const current = Date.now()
            setNow(current)
            const remaining = deadline - current
            const usedSincePing = lastActivity.current > lastPing.current

            if (usedSincePing && (current - lastPing.current >= PING_MS || remaining <= WARN_MS)) {
                if (!warningRef.current) void ping()
                return
            }
            if (remaining > WARN_MS || checking.current) return
            // The warning is up: check again only when the time is over.
            if (warningRef.current && remaining > 0) return

            // Before warning or signing out, ask the server: another tab may have kept the session alive.
            checking.current = true
            sessionStatus()
                .then((info) => {
                    apply(info)
                    const left = info.idle_expires_at ? new Date(info.idle_expires_at).getTime() - Date.now() : Infinity
                    if (left <= 0) expiredRef.current()
                    else setWarning(left <= WARN_MS)
                })
                .catch(failed)
                .finally(() => {
                    checking.current = false
                })
        }, 1000)
        return () => window.clearInterval(timer)
    }, [limit, deadline, ping, apply, failed])

    const keepGoing = async () => {
        setBusy(true)
        lastActivity.current = Date.now()
        if (await ping()) setWarning(false)
        setBusy(false)
    }

    if (!limit || !warning) return null

    return (
        <Dialog
            title="Your session is about to expire"
            subtitle={`You'll be signed out in ${clock(deadline - now)} because there has been no activity for a while.`}
            icon={<Clock size={18} />}
            onClose={() => void keepGoing()}
            className="session-timeout-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onSignOut}>
                        <LogOut size={15} /> Sign out
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" onClick={() => void keepGoing()} disabled={busy} data-autofocus>
                        {busy && <LoaderCircle size={15} className="entropy-spin" />} Continue session
                    </button>
                </>
            }
        >
            <p className="session-timeout-text">Click <strong>Continue session</strong> to stay signed in. Unsaved changes on this page are kept when you continue.</p>
        </Dialog>
    )
}
