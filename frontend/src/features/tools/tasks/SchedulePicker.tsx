import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { AlertTriangle, Bell, CalendarDays, ChevronLeft, ChevronRight, Repeat, X } from 'lucide-react'

import FloatingMenu from '../../../components/layout/FloatingMenu'
import {
    addDays,
    addMonths,
    dateLabel,
    firstDayOfWeek,
    isPastDue,
    monthGrid,
    nextWeekday,
    parseIso,
    repeatLabel,
    REPEATS,
    toIso,
    weekStart,
    type Schedule,
} from './schedule'

const TIMES = ['09:00', '12:00', '15:00', '18:00']
const EMPTY: Schedule = { date: '', time: '', repeat: '' }

/**
 * Choose a date, a time and how it repeats: a calendar, shortcuts for the usual choices,
 * and the browser's own time field. Nothing changes until Done, so looking is free.
 * A due time is optional; a reminder always has one.
 */
export default function SchedulePicker({
    kind,
    label,
    value,
    onChange,
    disabled = false,
    dueDate = '',
    badge,
}: {
    kind: 'due' | 'reminder'
    /** Empty when something outside already labels it. */
    label: string
    value: Schedule
    onChange: (value: Schedule) => void
    disabled?: boolean
    /** Offers "the day before" for a reminder. */
    dueDate?: string
    badge?: ReactNode
}) {
    const [open, setOpen] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)
    const today = toIso(new Date())
    const Icon = kind === 'due' ? CalendarDays : Bell

    const summary = value.date
        ? `${dateLabel(value.date, today)}${value.time ? ` · ${value.time}` : ''}`
        : kind === 'due'
          ? 'Set a due date'
          : 'Set a reminder'

    const close = () => {
        setOpen(false)
        triggerRef.current?.focus()
    }

    return (
        <div className="schedule-field">
            {(label || badge) && (
                <span className="schedule-field-label">
                    {label} {badge}
                </span>
            )}
            <div className="schedule-trigger-row">
                <button
                    ref={triggerRef}
                    type="button"
                    className={`schedule-trigger${value.date ? '' : ' is-empty'}`}
                    disabled={disabled}
                    aria-haspopup="dialog"
                    aria-expanded={open}
                    aria-label={`${label || (kind === 'due' ? 'Due date' : 'Reminder')}: ${summary}${value.repeat ? `, ${repeatLabel(value.repeat, value.date)}` : ''}`}
                    onClick={() => setOpen((current) => !current)}
                >
                    <Icon size={15} aria-hidden="true" />
                    <span className="schedule-trigger-text">
                        <span>{summary}</span>
                        {value.repeat && (
                            <small>
                                <Repeat size={11} aria-hidden="true" /> {repeatLabel(value.repeat, value.date)}
                            </small>
                        )}
                    </span>
                </button>
                {value.date && !disabled && (
                    <button
                        type="button"
                        className="schedule-clear"
                        aria-label={`Remove the ${kind === 'due' ? 'due date' : 'reminder'}`}
                        title="Remove"
                        onClick={() => onChange(EMPTY)}
                    >
                        <X size={14} aria-hidden="true" />
                    </button>
                )}
            </div>
            <FloatingMenu
                anchorRef={triggerRef}
                open={open}
                onClose={() => setOpen(false)}
                align="start"
                role="dialog"
                ariaLabel={kind === 'due' ? 'Choose the due date' : 'Choose the reminder'}
                className="schedule-panel"
            >
                <SchedulePanel
                    kind={kind}
                    initial={value}
                    today={today}
                    dueDate={dueDate}
                    onCancel={close}
                    onDone={(next) => {
                        onChange(next)
                        close()
                    }}
                />
            </FloatingMenu>
        </div>
    )
}

export function SchedulePanel({
    kind,
    initial,
    today,
    dueDate,
    onCancel,
    onDone,
}: {
    kind: 'due' | 'reminder'
    initial: Schedule
    today: string
    dueDate: string
    onCancel: () => void
    onDone: (value: Schedule) => void
}) {
    const [draft, setDraft] = useState<Schedule>(initial)
    // The day the keyboard is on; the month shown is the one it is in.
    const [cursor, setCursor] = useState(initial.date || today)
    const grid = useRef<HTMLTableElement>(null)
    const moved = useRef(false)
    const firstDay = useMemo(() => firstDayOfWeek(navigator.language), [])
    const days = useMemo(() => monthGrid(cursor, firstDay), [cursor, firstDay])
    const month = cursor.slice(0, 7)

    useEffect(() => {
        grid.current?.querySelector<HTMLElement>('button[tabindex="0"]')?.focus()
    }, [])

    useEffect(() => {
        if (moved.current) grid.current?.querySelector<HTMLElement>('button[tabindex="0"]')?.focus()
        moved.current = false
    }, [cursor])

    const moveTo = (next: string) => {
        moved.current = true
        setCursor(next)
    }

    const pick = (date: string) => {
        setCursor(date)
        setDraft((current) => ({ ...current, date, time: current.time || (kind === 'reminder' ? '09:00' : '') }))
    }

    const onKeyDown = (event: KeyboardEvent<HTMLTableElement>) => {
        const moves: Record<string, () => string> = {
            ArrowLeft: () => addDays(cursor, -1),
            ArrowRight: () => addDays(cursor, 1),
            ArrowUp: () => addDays(cursor, -7),
            ArrowDown: () => addDays(cursor, 7),
            Home: () => weekStart(cursor, firstDay),
            End: () => addDays(weekStart(cursor, firstDay), 6),
            PageUp: () => addMonths(cursor, event.shiftKey ? -12 : -1),
            PageDown: () => addMonths(cursor, event.shiftKey ? 12 : 1),
        }
        const move = moves[event.key]
        if (!move) return
        event.preventDefault()
        moveTo(move())
    }

    const presets =
        kind === 'due'
            ? [
                  { label: 'Today', date: today },
                  { label: 'Tomorrow', date: addDays(today, 1) },
                  { label: 'Next Monday', date: nextWeekday(today, 1) },
                  { label: 'In 2 weeks', date: addDays(today, 14) },
              ]
            : [
                  { label: 'Later today', date: today, time: laterToday() },
                  { label: 'Tomorrow 9:00', date: addDays(today, 1), time: '09:00' },
                  { label: 'Next Monday 9:00', date: nextWeekday(today, 1), time: '09:00' },
                  ...(dueDate && dueDate > today ? [{ label: 'Day before due', date: addDays(dueDate, -1), time: '09:00' }] : []),
              ]

    const inPast = kind === 'reminder' && draft.date !== '' && isPastDue(draft.date, draft.time || '00:00')
    const heading = parseIso(`${month}-01`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

    return (
        <div className="schedule-body">
            <div className="schedule-presets" role="group" aria-label="Quick choices">
                {presets.map((preset) => (
                    <button
                        key={preset.label}
                        type="button"
                        onClick={() => {
                            setCursor(preset.date)
                            setDraft((current) => ({
                                ...current,
                                date: preset.date,
                                time: 'time' in preset ? (preset.time as string) : current.time,
                            }))
                        }}
                    >
                        {preset.label}
                    </button>
                ))}
            </div>

            <div className="schedule-month">
                <button type="button" aria-label="Previous month" onClick={() => setCursor(addMonths(cursor, -1))}>
                    <ChevronLeft size={16} aria-hidden="true" />
                </button>
                <strong aria-live="polite">{heading}</strong>
                <button type="button" aria-label="Next month" onClick={() => setCursor(addMonths(cursor, 1))}>
                    <ChevronRight size={16} aria-hidden="true" />
                </button>
            </div>

            <table ref={grid} className="schedule-grid" role="grid" aria-label={heading} onKeyDown={onKeyDown}>
                <thead>
                    <tr>
                        {days.slice(0, 7).map((day) => (
                            <th key={day} scope="col" abbr={parseIso(day).toLocaleDateString(undefined, { weekday: 'long' })}>
                                {parseIso(day).toLocaleDateString(undefined, { weekday: 'narrow' })}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {Array.from({ length: 6 }, (_, week) => (
                        <tr key={week}>
                            {days.slice(week * 7, week * 7 + 7).map((day) => (
                                <td key={day} role="gridcell" aria-selected={day === draft.date}>
                                    <button
                                        type="button"
                                        tabIndex={day === cursor ? 0 : -1}
                                        className={[
                                            day === draft.date ? 'is-selected' : '',
                                            day === today ? 'is-today' : '',
                                            day.slice(0, 7) === month ? '' : 'is-outside',
                                            day < today ? 'is-past' : '',
                                        ].filter(Boolean).join(' ') || undefined}
                                        aria-current={day === today ? 'date' : undefined}
                                        aria-label={parseIso(day).toLocaleDateString(undefined, { dateStyle: 'full' })}
                                        onClick={() => pick(day)}
                                    >
                                        {parseIso(day).getDate()}
                                    </button>
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>

            <div className="schedule-row">
                <label className="schedule-time">
                    <span>{kind === 'due' ? 'Time (optional)' : 'Time'}</span>
                    <input
                        type="time"
                        value={draft.time}
                        disabled={!draft.date}
                        required={kind === 'reminder'}
                        onChange={(event) => setDraft((current) => ({ ...current, time: event.target.value }))}
                    />
                </label>
                <div className="schedule-times" role="group" aria-label="Common times">
                    {TIMES.map((time) => (
                        <button
                            key={time}
                            type="button"
                            aria-pressed={draft.time === time}
                            disabled={!draft.date}
                            onClick={() => setDraft((current) => ({ ...current, time }))}
                        >
                            {time}
                        </button>
                    ))}
                    {kind === 'due' && (
                        <button
                            type="button"
                            aria-pressed={draft.time === ''}
                            disabled={!draft.date}
                            onClick={() => setDraft((current) => ({ ...current, time: '' }))}
                        >
                            No time
                        </button>
                    )}
                </div>
            </div>

            <label className="schedule-repeat">
                <span>
                    <Repeat size={13} aria-hidden="true" /> Repeat
                </span>
                <select
                    className="entropy-select"
                    value={draft.repeat}
                    disabled={!draft.date}
                    onChange={(event) => setDraft((current) => ({ ...current, repeat: event.target.value }))}
                >
                    {REPEATS.map((item) => (
                        <option key={item.id} value={item.id}>{item.label}</option>
                    ))}
                </select>
            </label>

            <p className="schedule-note" role="status">
                {inPast ? (
                    <span className="is-warning">
                        <AlertTriangle size={13} aria-hidden="true" /> This time has passed, so the reminder would go out right away.
                    </span>
                ) : draft.repeat ? (
                    <>
                        {repeatLabel(draft.repeat, draft.date)}.{' '}
                        {kind === 'due'
                            ? 'Closing the task creates the next one.'
                            : 'It stops when the task is closed.'}
                    </>
                ) : !draft.date ? (
                    'Pick a day to continue.'
                ) : null}
            </p>

            <footer className="schedule-footer">
                <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={onCancel}>
                    Cancel
                </button>
                <button
                    type="button"
                    className="entropy-button entropy-button-primary entropy-button-sm"
                    disabled={!draft.date || (kind === 'reminder' && !draft.time)}
                    onClick={() => onDone(draft)}
                >
                    Done
                </button>
            </footer>
        </div>
    )
}

/** Three hours from now on the hour, but not past today's end. */
function laterToday(): string {
    const hour = Math.min(new Date().getHours() + 3, 23)
    return `${String(hour).padStart(2, '0')}:00`
}
