import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bell, CheckCircle2, CircleX, LoaderCircle, Megaphone, type LucideIcon } from 'lucide-react'

import type { AppNotification, NotificationLevel } from '../../api/notifications.api'
import { compareLabel, type ClashCompareBrief } from '../../api/clash.api'
import { runsApi, type Run } from '../../api/runs.api'
import { databaseSwitchDetail, databaseSwitchLabel, visionApi, type DatabaseSwitch, type VisionBroadcast } from '../../api/vision.api'
import { openRun, runIdFromHash } from '../../features/runs/navigation'
import { openDatabaseCompare } from '../../features/tools/clashNavigation'
import { openTask } from '../../features/tools/tasks/navigation'
import { subscribeVision, VISION_REFRESH_EVENT } from '../../features/vision/bus'
import { summarizeRuns, type RunsLevel } from '../../features/vision/runs'
import { PROJECT_CHANGED_EVENT, PROJECTS_UPDATED_EVENT } from '../../services/project'
import FloatingMenu from './FloatingMenu'
import { relativeTime } from './relativeTime'

const ACTIVE_POLL_MS = 1_000
const IDLE_POLL_MS = 3_000
/** Keep polling fast this long after the last active run: its result message follows. */
const FAST_AFTER_ACTIVE_MS = 10_000
const FLASH_MS = 6_000
/** More new messages than this flash once as a count, rather than one after another. */
const MAX_QUEUED_FLASHES = 3
const MAX_ACTIVITIES = 25
const STATUS_POLL_MS = 10_000
const SWITCH_POLL_MS = 1_000
const COMPARE_POLL_MS = 2_000

const LEVEL_ICONS: Record<NotificationLevel, LucideIcon> = {
    info: Bell,
    success: CheckCircle2,
    warning: AlertTriangle,
    error: CircleX,
}

/**
 * Vision's mark: the glyph of the Entropy logo, two linked steps, with the second
 * step solid as the live point. It pulses while something is running.
 */
function VisionMark({ live }: { live: boolean }) {
    return (
        <svg
            className={`vision-mark${live ? ' is-live' : ''}`}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            <rect x="1.5" y="1.5" width="9" height="9" rx="2.25" />
            <path d="M10.5 6h4.5a3 3 0 0 1 3 3v4.5" />
            <path d="M9 10.5v5.25a3 3 0 0 0 3 3h1.5" />
            <rect className="vision-mark-live" x="13.5" y="13.5" width="9" height="9" rx="2.25" fill="currentColor" />
        </svg>
    )
}

/**
 * The current project's active runs; empty when the user may not see runs. While
 * anything is active (and briefly after, as a result message may follow) both runs
 * and messages refresh fast, at the pace of the run screen.
 */
function useActiveRuns(onFastTick: () => void): Run[] {
    const [runs, setRuns] = useState<Run[]>([])

    useEffect(() => {
        let alive = true
        let timer: number | undefined
        let inFlight = false
        let lastActive = 0

        const load = async () => {
            if (inFlight) return
            window.clearTimeout(timer)
            let delay = IDLE_POLL_MS
            if (!document.hidden) {
                inFlight = true
                try {
                    const { items } = await runsApi.list({ tab: 'active', limit: 50 })
                    if (!alive) return
                    setRuns(items)
                    if (items.length) lastActive = Date.now()
                } catch {
                    if (!alive) return
                    setRuns([])
                } finally {
                    inFlight = false
                }
                if (Date.now() - lastActive < FAST_AFTER_ACTIVE_MS) {
                    delay = ACTIVE_POLL_MS
                    onFastTick()
                }
            }
            timer = window.setTimeout(() => void load(), delay)
        }

        const refresh = () => void load()
        refresh()
        window.addEventListener(PROJECT_CHANGED_EVENT, refresh)
        window.addEventListener('focus', refresh)
        // A run just started opens its screen; show it now rather than at the next poll.
        window.addEventListener('popstate', refresh)
        document.addEventListener('visibilitychange', refresh)
        return () => {
            alive = false
            window.clearTimeout(timer)
            window.removeEventListener(PROJECT_CHANGED_EVENT, refresh)
            window.removeEventListener('focus', refresh)
            window.removeEventListener('popstate', refresh)
            document.removeEventListener('visibilitychange', refresh)
        }
    }, [onFastTick])

    return runs
}

/** Go where a message points, if anywhere. */
function follow(notification: AppNotification): void {
    if (notification.source?.startsWith('run:')) openRun(Number(notification.source.slice(4)))
    else if (notification.source?.startsWith('task:')) openTask(Number(notification.source.slice(5)))
    else if (notification.source?.startsWith('clash:')) openDatabaseCompare()
}

function canFollow(notification: AppNotification): boolean {
    return Boolean(
        notification.source?.startsWith('run:') ||
            notification.source?.startsWith('task:') ||
            notification.source?.startsWith('clash:'),
    )
}

function dismissedStorageKey(username: string): string {
    return `entropy.vision.dismissedBroadcasts.${username}`
}

function storedDismissed(username: string): number[] {
    try {
        const value: unknown = JSON.parse(window.localStorage.getItem(dismissedStorageKey(username)) ?? '[]')
        return Array.isArray(value) ? value.filter((id): id is number => typeof id === 'number') : []
    } catch {
        return []
    }
}

/** Take the person to the question a run waits on; on its screen already, to the question. */
function goToWaitingRun(id: number): void {
    if (runIdFromHash(window.location.hash) !== id) {
        openRun(id)
        return
    }
    const prompts = document.querySelector('.run-prompts')
    prompts?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    prompts?.querySelector<HTMLElement>('input, select, textarea, button')?.focus({ preventScroll: true })
}

/** Whether Vision is on, and the messages for everyone; during an outage the last ones stay. */
function useVisionStatus(): { enabled: boolean | null; broadcasts: VisionBroadcast[]; database_switch?: DatabaseSwitch | null; clash_compare?: ClashCompareBrief | null; project_activity: boolean } {
    const [status, setStatus] = useState<{
        enabled: boolean | null
        broadcasts: VisionBroadcast[]
        project_activity: boolean
        database_switch?: DatabaseSwitch | null
        clash_compare?: ClashCompareBrief | null
    }>({
        enabled: null,
        broadcasts: [],
        // Until the project is known, only one's own runs.
        project_activity: false,
    })

    useEffect(() => {
        let alive = true
        const load = () => {
            if (document.hidden) return
            visionApi
                .status()
                .then((result) => {
                    if (alive) setStatus(result)
                })
                .catch(() => {
                    // A restarting server keeps its upgrade notice on screen; an older one has no API.
                    if (alive) setStatus((current) => ({ ...current, enabled: current.enabled ?? true }))
                })
        }
        load()
        const timer = window.setInterval(load, STATUS_POLL_MS)
        window.addEventListener('focus', load)
        // Another project may share less, or more: know before showing its runs.
        window.addEventListener(PROJECT_CHANGED_EVENT, load)
        window.addEventListener(PROJECTS_UPDATED_EVENT, load)
        window.addEventListener(VISION_REFRESH_EVENT, load)
        return () => {
            alive = false
            window.clearInterval(timer)
            window.removeEventListener(VISION_REFRESH_EVENT, load)
            window.removeEventListener('focus', load)
            window.removeEventListener(PROJECT_CHANGED_EVENT, load)
            window.removeEventListener(PROJECTS_UPDATED_EVENT, load)
        }
    }, [])

    // A switch moves quickly and concerns everyone: follow it closely while it lasts.
    const switching = Boolean(status.database_switch)
    useEffect(() => {
        if (!switching) return
        const timer = window.setInterval(() => window.dispatchEvent(new Event(VISION_REFRESH_EVENT)), SWITCH_POLL_MS)
        return () => window.clearInterval(timer)
    }, [switching])

    // No poll of its own: a comparison under way only makes this status read more often.
    const comparing = status.clash_compare?.state === 'analyzing' || status.clash_compare?.state === 'running'
    useEffect(() => {
        if (!comparing) return
        const timer = window.setInterval(() => window.dispatchEvent(new Event(VISION_REFRESH_EVENT)), COMPARE_POLL_MS)
        return () => window.clearInterval(timer)
    }, [comparing])

    return status
}

type VisionProps = {
    username: string
    notifications: AppNotification[]
    loaded: boolean
    onMarkRead: (id: number) => void
    onRefreshNotifications: () => void
}

/** Nothing at all while an administrator has Vision turned off. */
export default function Vision(props: VisionProps) {
    const { enabled, broadcasts, database_switch: databaseSwitch, clash_compare: compare, project_activity: projectActivity } = useVisionStatus()
    return enabled ? <VisionIsland {...props} broadcasts={broadcasts}
            databaseSwitch={databaseSwitch ?? null} compare={compare ?? null} projectActivity={projectActivity} /> : null
}

/**
 * Vision: the live island in the topbar. It flashes new messages (task updates,
 * reminders, due dates, run results), otherwise shows what is running, and opens
 * into a list of both.
 */
function VisionIsland({
    username,
    notifications,
    loaded,
    onMarkRead,
    onRefreshNotifications,
    broadcasts,
    databaseSwitch,
    compare,
    projectActivity,
}: VisionProps & { broadcasts: VisionBroadcast[]; databaseSwitch: DatabaseSwitch | null; compare: ClashCompareBrief | null; projectActivity: boolean }) {
    const runs = useActiveRuns(onRefreshNotifications)
    const activity = summarizeRuns(runs, username, projectActivity)
    const [open, setOpen] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)
    // Messages up to this id have been flashed, or were there when the page opened.
    const [cursor, setCursor] = useState<number | null>(null)
    const [dismissed, setDismissed] = useState(() => storedDismissed(username))
    // What modules reported on this page; gone on reload. The bell keeps server messages.
    const [reported, setReported] = useState<AppNotification[]>([])
    const [reportedFlashes, setReportedFlashes] = useState<AppNotification[]>([])

    // A comparison that just ended has left a message: show it now, not at the next poll.
    const comparing = compare !== null
    const wasComparing = useRef(comparing)
    useEffect(() => {
        if (wasComparing.current && !comparing) onRefreshNotifications()
        wasComparing.current = comparing
    }, [comparing, onRefreshNotifications])

    useEffect(() => {
        let nextId = 0
        return subscribeVision((event) => {
            // Negative: never confused with the server's message ids.
            nextId -= 1
            const entry: AppNotification = {
                id: nextId,
                title: event.title,
                message: event.message,
                level: event.level,
                source: null,
                read: true,
                created_at: new Date().toISOString(),
            }
            setReported((current) => [entry, ...current].slice(0, MAX_ACTIVITIES))
            // Vision replaces the toast here; when a toast shows it, one is enough.
            if (event.flash) setReportedFlashes((current) => [...current, entry])
        })
    }, [])

    if (loaded && cursor === null) {
        setCursor(notifications.reduce((highest, item) => Math.max(highest, item.id), 0))
    }

    const pending = cursor === null
        ? []
        : notifications.filter((item) => !item.read && item.id > cursor).sort((a, b) => a.id - b.id)
    const queued = pending.length + reportedFlashes.length
    const summary = queued > MAX_QUEUED_FLASHES
    const flash = summary ? null : pending[0] ?? reportedFlashes[0] ?? null
    // What ending the current flash moves past: one message, or everything in a summary.
    const serverEnd = summary ? pending[pending.length - 1]?.id ?? null : flash && flash.id > 0 ? flash.id : null
    const reportedEnd = summary ? 'all' : flash && flash.id < 0 ? 'first' : null
    const flashKey = summary ? `summary:${queued}` : flash ? String(flash.id) : null

    const endFlash = useCallback((server: number | null, local: 'all' | 'first' | null) => {
        if (server !== null) setCursor(server)
        if (local === 'all') setReportedFlashes([])
        if (local === 'first') setReportedFlashes((current) => current.slice(1))
    }, [])

    useEffect(() => {
        if (flashKey === null) return
        const timer = window.setTimeout(() => endFlash(serverEnd, reportedEnd), FLASH_MS)
        return () => window.clearTimeout(timer)
    }, [flashKey, serverEnd, reportedEnd, endFlash])

    const announcements = broadcasts.filter((item) => !dismissed.includes(item.id))
    const announcement = announcements[0] ?? null
    const flashing = summary || flash !== null
    // What waits on this person's own run still comes first.
    const showCompare = compare !== null && activity.level !== 'waiting'
    const compareWaiting = showCompare && compare.state === 'waiting'
    // A message passes; what everyone must know comes next; then what needs this person.
    const level: NotificationLevel | RunsLevel = summary
        ? 'info'
        : flash
          ? flash.level
          : databaseSwitch
            ? 'running'
            : announcement
              ? announcement.level
              : compareWaiting
                ? 'waiting'
                : showCompare
                  ? 'running'
                  : activity.level
    const FlashIcon = flash ? LEVEL_ICONS[flash.level] : Bell
    // Nothing to say: the island shows only its mark.
    const idle =
        !summary && !flash && !databaseSwitch && !announcement && !showCompare && activity.level === 'idle'

    const onClick = () => {
        if (flash && canFollow(flash)) {
            // In this order: marking read redraws the shell, which then reads the new hash.
            follow(flash)
            onMarkRead(flash.id)
            endFlash(serverEnd, reportedEnd)
            return
        }
        if (flashKey !== null) {
            endFlash(serverEnd, reportedEnd)
        } else if (!announcement && compareWaiting) {
            openDatabaseCompare()
            return
        } else if (!announcement && activity.open !== null) {
            goToWaitingRun(activity.open)
            return
        }
        setOpen((value) => !value)
    }

    const dismiss = (id: number) => {
        const next = [...dismissed, id].slice(-50)
        setDismissed(next)
        try {
            window.localStorage.setItem(dismissedStorageKey(username), JSON.stringify(next))
        } catch {
            // Storage may be unavailable (private mode); it stays dismissed until reload.
        }
    }

    // Newest first. Only this page's messages: the bell is the one lasting history.
    const activities = reported

    const clearActivities = () => {
        setReported([])
        // Nothing just cleared should still flash.
        setReportedFlashes([])
    }

    // The whole message, for the tooltip and screen readers; the island shows one line.
    const flashText = flash ? [flash.title, flash.message].filter(Boolean).join(': ') : ''

    const runRow = (run: Run, mine: boolean) => (
        <button
            key={run.id}
            type="button"
            role="menuitem"
            onClick={() => {
                setOpen(false)
                goToWaitingRun(run.id)
            }}
        >
            {run.waiting_for_input ? (
                <AlertTriangle size={15} className="vision-level is-warning" aria-hidden="true" />
            ) : (
                <LoaderCircle size={15} className="entropy-spin" aria-hidden="true" />
            )}
            <span className="vision-item">
                <strong>Run #{run.id}: {run.target || run.workflow}</strong>
                <small>
                    {!mine && <span className="vision-owner">{run.username || 'Someone'} · </span>}
                    {run.kind === 'plugin' ? 'Plugin' : 'Workflow'} ·{' '}
                    {run.waiting_for_input ? `waiting for ${mine ? 'you' : run.username || 'input'}` : run.state} · {run.node}
                </small>
            </span>
        </button>
    )

    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                className={`vision is-${level}${flashing || announcement ? ' is-flash' : ''}${idle ? ' is-idle' : ''}`}
                onClick={onClick}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-label={idle ? 'Vision' : undefined}
                title={
                    flash
                        ? flashText
                        : announcement && !flashing
                          ? announcement.message
                          : 'Vision: what is running, and new messages'
                }
            >
                {summary ? (
                    <>
                        <Bell size={14} aria-hidden="true" />
                        <span className="vision-text"><strong>{queued} new messages</strong></span>
                    </>
                ) : flash ? (
                    <>
                        <FlashIcon size={14} aria-hidden="true" />
                        <span className="vision-text"><strong>{flash.title}</strong></span>
                    </>
                ) : databaseSwitch ? (
                    <>
                        <LoaderCircle size={14} className="entropy-spin" aria-hidden="true" />
                        <span className="vision-text"><strong>{databaseSwitchLabel(databaseSwitch)}</strong></span>
                    </>
                ) : announcement ? (
                    <>
                        <Megaphone size={14} aria-hidden="true" />
                        <span className="vision-text"><strong>{announcement.message}</strong></span>
                    </>
                ) : compareWaiting ? (
                    <>
                        <AlertTriangle size={14} aria-hidden="true" />
                        <span className="vision-text"><strong>{compareLabel(compare)}</strong></span>
                    </>
                ) : showCompare ? (
                    <>
                        <VisionMark live />
                        <span className="vision-text"><strong>{compareLabel(compare)}</strong></span>
                    </>
                ) : activity.level === 'waiting' || activity.level === 'waiting-others' ? (
                    <>
                        <AlertTriangle size={14} aria-hidden="true" />
                        <span className="vision-text"><strong>{activity.label}</strong></span>
                    </>
                ) : activity.level !== 'idle' ? (
                    <>
                        <VisionMark live={activity.level === 'running'} />
                        <span className="vision-text"><strong>{activity.label}</strong></span>
                    </>
                ) : (
                    // Idle: the mark alone; its name is for screen readers.
                    <VisionMark live={false} />
                )}
            </button>

            {/* Read out once per message; the running label changes too often to announce. */}
            <span className="vision-announce" role="status" aria-live="polite">
                {summary
                    ? `${queued} new messages`
                    : flash
                      ? flash.level === 'error'
                          ? ''
                          : flashText
                      : announcement?.message ??
                        (compareWaiting ? compareLabel(compare) : activity.level.startsWith('waiting') ? activity.label : '')}
            </span>
            {/* Errors interrupt, as the error toasts did. */}
            <span className="vision-announce" role="alert" aria-live="assertive">
                {!summary && flash?.level === 'error' ? flashText : ''}
            </span>

            <FloatingMenu anchorRef={triggerRef} open={open} onClose={() => setOpen(false)} className="topbar-create-menu vision-menu">
                {databaseSwitch && (
                    <>
                        <span className="topbar-create-label">Database</span>
                        <div className="vision-broadcast-row is-info">
                            <LoaderCircle size={15} className="entropy-spin" aria-hidden="true" />
                            <div>
                                <p>{databaseSwitchLabel(databaseSwitch)}</p>
                                <small>{databaseSwitchDetail(databaseSwitch)}</small>
                            </div>
                        </div>
                    </>
                )}
                {announcements.length > 0 && <span className="topbar-create-label">For everyone</span>}
                {announcements.map((item) => (
                    <div key={item.id} className={`vision-broadcast-row is-${item.level}`}>
                        <Megaphone size={15} aria-hidden="true" />
                        <div>
                            <p>{item.message}</p>
                            <small>From {item.created_by} · {relativeTime(item.created_at)}</small>
                            <div>
                                <button type="button" onClick={() => dismiss(item.id)}>Dismiss</button>
                            </div>
                        </div>
                    </div>
                ))}

                {compare && (
                    <>
                        <span className="topbar-create-label">Database compare</span>
                        <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                                setOpen(false)
                                openDatabaseCompare()
                            }}
                        >
                            {compare.state === 'waiting' ? (
                                <AlertTriangle size={15} className="vision-level is-warning" aria-hidden="true" />
                            ) : (
                                <LoaderCircle size={15} className="entropy-spin" aria-hidden="true" />
                            )}
                            <span className="vision-item">
                                <strong>{compareLabel(compare)}</strong>
                                <small>
                                    {compare.left} and {compare.right}
                                    {compare.current ? ` · ${compare.current}` : ''}
                                </small>
                            </span>
                        </button>
                    </>
                )}

                <span className="topbar-create-label">Your runs</span>
                {activity.mine.length ? (
                    activity.mine.map((run) => runRow(run, true))
                ) : (
                    <p className="vision-empty">You have nothing running in this project.</p>
                )}

                {projectActivity && activity.others.length > 0 && (
                    <>
                        <span className="topbar-create-label">Others in this project</span>
                        {activity.others.map((run) => runRow(run, false))}
                    </>
                )}

                <div className="vision-section">
                    <span className="topbar-create-label">This session</span>
                    {activities.length > 0 && (
                        <button type="button" className="vision-clear" onClick={clearActivities}>
                            Clear
                        </button>
                    )}
                </div>
                {activities.length ? (
                    activities.map((item) => {
                        const Icon = LEVEL_ICONS[item.level]
                        return (
                            <button
                                key={item.id}
                                type="button"
                                role="menuitem"
                                className={item.read ? 'is-read' : undefined}
                                onClick={() => {
                                    setOpen(false)
                                    follow(item)
                                    if (!item.read) onMarkRead(item.id)
                                }}
                            >
                                <Icon size={15} className={`vision-level is-${item.level}`} aria-hidden="true" />
                                <span className="vision-item">
                                    <strong>{item.title}</strong>
                                    {item.message && <small>{item.message}</small>}
                                    <time dateTime={item.created_at}>{relativeTime(item.created_at)}</time>
                                </span>
                            </button>
                        )
                    })
                ) : (
                    <p className="vision-empty">No messages yet. Notifications stay under the bell.</p>
                )}
            </FloatingMenu>
        </>
    )
}
