import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import {
    ArrowLeft,
    ArrowRight,
    Check,
    ExternalLink,
    GripVertical,
    LayoutGrid,
    LoaderCircle,
    Plus,
    RefreshCw,
    RotateCcw,
    Settings2,
    SlidersHorizontal,
    X,
} from 'lucide-react'

import {
    getDashboardLayout,
    resetDashboardLayout,
    saveDashboardLayout,
    type DashboardLayout,
    type DashboardWidget,
    type WidgetSize,
} from '../../api/preferences.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { openTool } from './widgets/core'
import { createWidget, defaultWidgets, findWidget, WIDGETS, type WidgetDefinition, type WidgetSetting } from './widgets/registry'
import EntropyLoader from '../../components/feedback/EntropyLoader'

const SIZES: Array<[WidgetSize, string]> = [
    ['small', 'Small'],
    ['medium', 'Half'],
    ['large', 'Wide'],
    ['full', 'Full width'],
]

const REFRESH: Array<[number, string]> = [
    [5, 'Every 5 seconds'],
    [15, 'Every 15 seconds'],
    [30, 'Every 30 seconds'],
    [60, 'Every minute'],
    [300, 'Every 5 minutes'],
    [0, 'Off'],
]

function openPage(page: string): void {
    window.history.pushState(null, '', `#/${page}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
}

export default function Dashboard() {
    const { notify, modal } = useFeedback()
    const [layout, setLayout] = useState<DashboardLayout | null>(null)
    const [editing, setEditing] = useState(false)
    const [galleryOpen, setGalleryOpen] = useState(false)
    const [settingsFor, setSettingsFor] = useState<string | null>(null)
    const [saving, setSaving] = useState(false)
    const [tick, setTick] = useState(0)
    const [force, setForce] = useState(0)
    const [dragging, setDragging] = useState<string | null>(null)
    const saveTimer = useRef<number | undefined>(undefined)

    useEffect(() => {
        getDashboardLayout()
            .then((stored) =>
                setLayout(stored.customized ? stored : { ...stored, widgets: defaultWidgets(), refresh_seconds: stored.refresh_seconds }),
            )
            .catch(() => setLayout({ widgets: defaultWidgets(), refresh_seconds: 5, customized: false }))
    }, [])

    const refreshSeconds = layout?.refresh_seconds ?? 5
    useEffect(() => {
        if (!refreshSeconds) return
        const timer = window.setInterval(() => setTick((value) => value + 1), refreshSeconds * 1000)
        return () => window.clearInterval(timer)
    }, [refreshSeconds])

    // Every change is saved shortly after it is made.
    const change = useCallback(
        (next: DashboardLayout) => {
            setLayout({ ...next, customized: true })
            window.clearTimeout(saveTimer.current)
            saveTimer.current = window.setTimeout(() => {
                setSaving(true)
                saveDashboardLayout(next)
                    .catch((cause: unknown) =>
                        notify.error((cause as Error).message, { title: 'Unable to save the dashboard' }),
                    )
                    .finally(() => setSaving(false))
            }, 500)
        },
        [notify],
    )
    useEffect(() => () => window.clearTimeout(saveTimer.current), [])

    const updateWidget = (id: string, patch: Partial<DashboardWidget>) =>
        layout && change({ ...layout, widgets: layout.widgets.map((widget) => (widget.id === id ? { ...widget, ...patch } : widget)) })

    const removeWidget = (id: string) => layout && change({ ...layout, widgets: layout.widgets.filter((widget) => widget.id !== id) })

    const move = (id: string, to: number) => {
        if (!layout) return
        const widgets = [...layout.widgets]
        const from = widgets.findIndex((widget) => widget.id === id)
        if (from < 0 || to < 0 || to >= widgets.length || from === to) return
        const [item] = widgets.splice(from, 1)
        widgets.splice(to, 0, item)
        change({ ...layout, widgets })
    }

    const addWidget = (definition: WidgetDefinition) => {
        if (!layout) return
        const widget = createWidget(definition)
        change({ ...layout, widgets: [...layout.widgets, widget] })
        setGalleryOpen(false)
        setEditing(true)
        notify.success(`${definition.name} added at the end of the dashboard.`, { title: 'Widget added' })
        window.setTimeout(() => document.getElementById(`widget-${widget.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50)
    }

    const reset = async () => {
        const confirmed = await modal.confirm({
            title: 'Reset the dashboard?',
            message: 'Your widgets and their settings are replaced by the default ones.',
            confirmText: 'Reset dashboard',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        window.clearTimeout(saveTimer.current)
        try {
            const stored = await resetDashboardLayout()
            setLayout({ ...stored, widgets: defaultWidgets() })
            setSettingsFor(null)
        } catch (cause) {
            notify.error((cause as Error).message, { title: 'Unable to reset the dashboard' })
        }
    }

    const onDrop = (event: DragEvent, target: string) => {
        event.preventDefault()
        if (!layout || !dragging || dragging === target) return
        move(dragging, layout.widgets.findIndex((widget) => widget.id === target))
        setDragging(null)
    }

    if (!layout) {
        return (
            <section className="dashboard-page">
                <EntropyLoader label="Loading your dashboard…" />
            </section>
        )
    }

    return (
        <section className={`dashboard-page${editing ? ' is-editing' : ''}`}>
            <header className="page-toolbar dashboard-toolbar">
                {editing ? (
                    <p className="dashboard-edit-hint">
                        Drag widgets to reorder them, change their size, settings or remove them. Changes are saved as you go.
                        {saving && <LoaderCircle size={14} className="entropy-spin" aria-label="Saving" />}
                    </p>
                ) : (
                    <span />
                )}
                <div className="dashboard-refresh-controls">
                    <select
                        className="dashboard-refresh-select"
                        value={layout.refresh_seconds}
                        aria-label="Automatic refresh"
                        title="Run widgets follow this; tool widgets refresh at most every 30 seconds"
                        onChange={(event) => change({ ...layout, refresh_seconds: Number(event.target.value) })}
                    >
                        {REFRESH.map(([value, label]) => (
                            <option key={value} value={value}>
                                {value ? `Refresh: ${label.toLowerCase()}` : 'Refresh: off'}
                            </option>
                        ))}
                    </select>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => setForce((value) => value + 1)}
                        title="Refresh all widgets now"
                    >
                        <RefreshCw size={16} />
                        Refresh
                    </button>
                    {editing && (
                        <button type="button" className="entropy-button entropy-button-ghost" onClick={() => void reset()}>
                            <RotateCcw size={16} />
                            Reset
                        </button>
                    )}
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={() => setGalleryOpen(true)}>
                        <Plus size={16} />
                        Add widget
                    </button>
                    <button
                        type="button"
                        className={`entropy-button ${editing ? 'entropy-button-primary' : 'entropy-button-secondary'}`}
                        aria-pressed={editing}
                        onClick={() => {
                            setEditing((value) => !value)
                            setSettingsFor(null)
                        }}
                    >
                        {editing ? <Check size={16} /> : <SlidersHorizontal size={16} />}
                        {editing ? 'Done' : 'Customize'}
                    </button>
                </div>
            </header>

            {layout.widgets.length === 0 ? (
                <div className="dashboard-empty dashboard-empty-board">
                    <LayoutGrid size={26} />
                    <strong>Your dashboard is empty</strong>
                    <p>Add widgets for runs, tasks, releases and the other tools you use.</p>
                    <button type="button" className="entropy-button entropy-button-primary" onClick={() => setGalleryOpen(true)}>
                        <Plus size={16} /> Add widget
                    </button>
                </div>
            ) : (
                <div className="dashboard-grid">
                    {layout.widgets.map((widget, index) => {
                        const definition = findWidget(widget.type)
                        return (
                            <WidgetFrame
                                key={widget.id}
                                widget={widget}
                                definition={definition}
                                editing={editing}
                                dragging={dragging === widget.id}
                                settingsOpen={settingsFor === widget.id}
                                position={index}
                                count={layout.widgets.length}
                                tick={tick}
                                force={force}
                                onDragStart={() => setDragging(widget.id)}
                                onDragEnd={() => setDragging(null)}
                                onDrop={(event) => onDrop(event, widget.id)}
                                onMove={(to) => move(widget.id, to)}
                                onSize={(size) => updateWidget(widget.id, { size })}
                                onSettings={(settings) => updateWidget(widget.id, { settings })}
                                onToggleSettings={() => setSettingsFor((current) => (current === widget.id ? null : widget.id))}
                                onRemove={() => removeWidget(widget.id)}
                            />
                        )
                    })}
                    {editing && (
                        <button type="button" className="dashboard-add-tile" onClick={() => setGalleryOpen(true)}>
                            <Plus size={20} />
                            Add widget
                        </button>
                    )}
                </div>
            )}

            {galleryOpen && (
                <WidgetGallery
                    used={layout.widgets.map((widget) => widget.type)}
                    onAdd={addWidget}
                    onClose={() => setGalleryOpen(false)}
                />
            )}
        </section>
    )
}

function WidgetFrame({
    widget,
    definition,
    editing,
    dragging,
    settingsOpen,
    position,
    count,
    tick,
    force,
    onDragStart,
    onDragEnd,
    onDrop,
    onMove,
    onSize,
    onSettings,
    onToggleSettings,
    onRemove,
}: {
    widget: DashboardWidget
    definition: WidgetDefinition | null
    editing: boolean
    dragging: boolean
    settingsOpen: boolean
    position: number
    count: number
    tick: number
    force: number
    onDragStart: () => void
    onDragEnd: () => void
    onDrop: (event: DragEvent) => void
    onMove: (to: number) => void
    onSize: (size: WidgetSize) => void
    onSettings: (settings: Record<string, unknown>) => void
    onToggleSettings: () => void
    onRemove: () => void
}) {
    const [over, setOver] = useState(false)
    const Icon = definition?.icon ?? LayoutGrid
    const title = String(widget.settings.title ?? '').trim() || definition?.name || 'Unknown widget'
    const settings = useMemo(() => ({ ...definition?.defaults, ...widget.settings }), [definition, widget.settings])
    const Component = definition?.component

    return (
        <article
            id={`widget-${widget.id}`}
            className={`dashboard-widget dashboard-widget-${widget.size}${dragging ? ' is-dragging' : ''}${over ? ' is-over' : ''}`}
            aria-label={title}
            draggable={editing}
            onDragStart={(event) => {
                event.dataTransfer.effectAllowed = 'move'
                event.dataTransfer.setData('text/plain', widget.id)
                onDragStart()
            }}
            onDragEnd={onDragEnd}
            onDragOver={(event) => {
                if (!editing) return
                event.preventDefault()
                setOver(true)
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(event) => {
                setOver(false)
                onDrop(event)
            }}
        >
            <header className="dashboard-widget-head">
                {editing && <GripVertical size={16} className="dashboard-widget-grip" aria-hidden="true" />}
                <span className="dashboard-widget-icon" aria-hidden="true">
                    <Icon size={16} />
                </span>
                <h2>{title}</h2>
                {editing ? (
                    <span className="dashboard-widget-tools">
                        <select
                            value={widget.size}
                            aria-label={`Size of ${title}`}
                            onChange={(event) => onSize(event.target.value as WidgetSize)}
                        >
                            {SIZES.map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </select>
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                            aria-label={`Move ${title} earlier`}
                            disabled={position === 0}
                            onClick={() => onMove(position - 1)}
                        >
                            <ArrowLeft size={14} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                            aria-label={`Move ${title} later`}
                            disabled={position === count - 1}
                            onClick={() => onMove(position + 1)}
                        >
                            <ArrowRight size={14} />
                        </button>
                        <button
                            type="button"
                            className={`entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm${settingsOpen ? ' is-active' : ''}`}
                            aria-label={`Settings of ${title}`}
                            aria-expanded={settingsOpen}
                            onClick={onToggleSettings}
                        >
                            <Settings2 size={14} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                            aria-label={`Remove ${title}`}
                            onClick={onRemove}
                        >
                            <X size={14} />
                        </button>
                    </span>
                ) : (
                    (definition?.tool || definition?.page) && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm dashboard-widget-open"
                            onClick={() => (definition.tool ? openTool(definition.tool) : openPage(definition.page ?? ''))}
                        >
                            Open <ExternalLink size={13} />
                        </button>
                    )
                )}
            </header>
            {editing && settingsOpen && (
                <WidgetSettingsForm definition={definition} settings={settings} onChange={onSettings} />
            )}
            <div className="dashboard-widget-body">
                {Component ? (
                    <Component settings={settings} tick={tick} force={force} />
                ) : (
                    <p className="dw-empty">This widget is no longer available. Remove it in Customize.</p>
                )}
            </div>
        </article>
    )
}

function WidgetSettingsForm({
    definition,
    settings,
    onChange,
}: {
    definition: WidgetDefinition | null
    settings: Record<string, unknown>
    onChange: (settings: Record<string, unknown>) => void
}) {
    const fields: WidgetSetting[] = [
        { key: 'title', label: 'Title', kind: 'text', placeholder: definition?.name },
        ...(definition?.settings ?? []),
    ]
    const set = (key: string, value: unknown) => onChange({ ...settings, [key]: value })
    return (
        <div className="dashboard-widget-settings">
            {fields.map((field) => (
                <label key={field.key} className={field.kind === 'toggle' ? 'is-toggle' : undefined}>
                    <span>{field.label}</span>
                    {field.kind === 'select' ? (
                        <select value={String(settings[field.key] ?? '')} onChange={(event) => set(field.key, event.target.value)}>
                            {field.options.map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    ) : field.kind === 'number' ? (
                        <input
                            type="number"
                            min={field.min}
                            max={field.max}
                            value={String(settings[field.key] ?? '')}
                            onChange={(event) => {
                                const value = Number(event.target.value)
                                if (Number.isInteger(value)) set(field.key, Math.min(field.max, Math.max(field.min, value)))
                            }}
                        />
                    ) : field.kind === 'toggle' ? (
                        <input
                            type="checkbox"
                            checked={settings[field.key] !== false}
                            onChange={(event) => set(field.key, event.target.checked)}
                        />
                    ) : (
                        <input
                            type="text"
                            maxLength={80}
                            value={String(settings[field.key] ?? '')}
                            placeholder={field.placeholder}
                            onChange={(event) => set(field.key, event.target.value)}
                        />
                    )}
                </label>
            ))}
        </div>
    )
}

function WidgetGallery({
    used,
    onAdd,
    onClose,
}: {
    used: string[]
    onAdd: (definition: WidgetDefinition) => void
    onClose: () => void
}) {
    const [query, setQuery] = useState('')
    const needle = query.trim().toLowerCase()
    const shown = WIDGETS.filter(
        (widget) => !needle || `${widget.name} ${widget.description} ${widget.group}`.toLowerCase().includes(needle),
    )
    return (
        <Dialog
            title="Add a widget"
            subtitle="Widgets show the active project's data. A widget can be added more than once, with other settings."
            icon={<LayoutGrid size={18} />}
            onClose={onClose}
            className="dashboard-gallery-dialog"
        >
            <input
                className="dashboard-gallery-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search widgets…"
                aria-label="Search widgets"
                autoFocus
            />
            {(['Runs', 'Tools'] as const).map((group) => {
                const items = shown.filter((widget) => widget.group === group)
                if (!items.length) return null
                return (
                    <section key={group} className="dashboard-gallery-group">
                        <h3>{group}</h3>
                        <div className="dashboard-gallery">
                            {items.map((widget) => {
                                const Icon = widget.icon
                                const count = used.filter((type) => type === widget.type).length
                                return (
                                    <button
                                        key={widget.type}
                                        type="button"
                                        className="dashboard-gallery-card"
                                        onClick={() => onAdd(widget)}
                                    >
                                        <span className="dashboard-gallery-icon">
                                            <Icon size={18} />
                                        </span>
                                        <span className="dashboard-gallery-text">
                                            <strong>
                                                {widget.name}
                                                {count > 0 && <small> · on the dashboard{count > 1 ? ` (${count})` : ''}</small>}
                                            </strong>
                                            <span>{widget.description}</span>
                                        </span>
                                        <Plus size={16} className="dashboard-gallery-add" aria-hidden="true" />
                                    </button>
                                )
                            })}
                        </div>
                    </section>
                )
            })}
            {shown.length === 0 && <p className="dw-empty">No widget matches “{query}”.</p>}
        </Dialog>
    )
}
