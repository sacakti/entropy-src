/**
 * Dashboard widgets.
 *
 * Adding a widget is adding an entry here: the "Add widget" gallery, the
 * settings form and the dashboard are built from this list. A dashboard
 * may hold several widgets of one type (two task lists with different
 * filters), each with its own size and settings.
 */
import type { ComponentType } from 'react'
import {
    Activity,
    Archive,
    Bird,
    CalendarClock,
    GitBranch,
    History,
    LayoutGrid,
    ListTodo,
    PackageCheck,
    PlayCircle,
    type LucideIcon,
} from 'lucide-react'

import type { DashboardWidget, WidgetSize } from '../../../api/preferences.api'
import { ActiveRunsWidget, RecentRunsWidget, RunSummaryWidget } from './RunWidgets'
import {
    ArtifactsWidget,
    EagleHistoryWidget,
    GitRepositoriesWidget,
    ReleasesWidget,
    SchedulesWidget,
    TasksWidget,
    ToolLauncherWidget,
} from './ToolWidgets'
import type { WidgetProps } from './core'

export type WidgetSetting =
    | { key: string; label: string; kind: 'select'; options: Array<[string, string]> }
    | { key: string; label: string; kind: 'number'; min: number; max: number }
    | { key: string; label: string; kind: 'text'; placeholder?: string }
    | { key: string; label: string; kind: 'toggle' }

export type WidgetDefinition = {
    type: string
    name: string
    description: string
    group: 'Runs' | 'Tools'
    icon: LucideIcon
    /** The tool it shows, opened from the widget's header. */
    tool?: string
    page?: string
    size: WidgetSize
    settings?: WidgetSetting[]
    defaults?: Record<string, unknown>
    component: ComponentType<WidgetProps>
}

const LIMIT = (max: number): WidgetSetting => ({ key: 'limit', label: 'Rows', kind: 'number', min: 1, max })

export const WIDGETS: WidgetDefinition[] = [
    {
        type: 'runs.summary',
        name: 'Run summary',
        description: 'Runs of the project by state: total, running, queued, completed and failed.',
        group: 'Runs',
        icon: Activity,
        page: 'runs',
        size: 'full',
        component: RunSummaryWidget,
    },
    {
        type: 'runs.active',
        name: 'Active runs',
        description: 'Runs that are queued, starting, running or paused.',
        group: 'Runs',
        icon: PlayCircle,
        page: 'runs?tab=active',
        size: 'medium',
        settings: [LIMIT(8)],
        defaults: { limit: 8 },
        component: ActiveRunsWidget,
    },
    {
        type: 'runs.recent',
        name: 'Recent runs',
        description: 'The latest completed, failed and cancelled runs.',
        group: 'Runs',
        icon: History,
        page: 'runs?tab=all',
        size: 'medium',
        settings: [LIMIT(8)],
        defaults: { limit: 8 },
        component: RecentRunsWidget,
    },
    {
        type: 'schedules.upcoming',
        name: 'Upcoming schedules',
        description: 'The next scheduled runs, and failed scheduled runs to look at.',
        group: 'Runs',
        icon: CalendarClock,
        page: 'schedulers',
        size: 'medium',
        settings: [LIMIT(20)],
        defaults: { limit: 6 },
        component: SchedulesWidget,
    },
    {
        type: 'tasks.list',
        name: 'Tasks',
        description: 'Your tasks or the project’s open tasks: add one, tick one off.',
        group: 'Tools',
        icon: ListTodo,
        tool: 'tasks',
        size: 'medium',
        settings: [
            {
                key: 'filter',
                label: 'Show',
                kind: 'select',
                options: [
                    ['mine', 'Assigned to me'],
                    ['open', 'Open tasks'],
                    ['done', 'Done tasks'],
                    ['all', 'All tasks'],
                ],
            },
            LIMIT(30),
            { key: 'quick_add', label: 'Add tasks from the widget', kind: 'toggle' },
        ],
        defaults: { filter: 'mine', limit: 8, quick_add: true },
        component: TasksWidget,
    },
    {
        type: 'releases.board',
        name: 'Releases',
        description: 'Releases by stage, and the latest ones with their open tasks.',
        group: 'Tools',
        icon: PackageCheck,
        tool: 'release-manager',
        size: 'medium',
        settings: [{ key: 'environment', label: 'Environment', kind: 'text', placeholder: 'All environments' }, LIMIT(20)],
        defaults: { environment: '', limit: 6 },
        component: ReleasesWidget,
    },
    {
        type: 'artifacts.recent',
        name: 'Artifacts',
        description: 'The latest packages and generated files, ready to download.',
        group: 'Tools',
        icon: Archive,
        tool: 'artifacts',
        size: 'medium',
        settings: [
            {
                key: 'classification',
                label: 'Show',
                kind: 'select',
                options: [
                    ['all', 'All artifacts'],
                    ['added', 'Added (uploads and paths)'],
                    ['generated', 'Generated by runs'],
                ],
            },
            LIMIT(20),
        ],
        defaults: { classification: 'all', limit: 6 },
        component: ArtifactsWidget,
    },
    {
        type: 'git.repositories',
        name: 'Git repositories',
        description: 'The project’s repositories and yours, with their clone paths.',
        group: 'Tools',
        icon: GitBranch,
        tool: 'git-repositories',
        size: 'medium',
        settings: [LIMIT(20)],
        defaults: { limit: 6 },
        component: GitRepositoriesWidget,
    },
    {
        type: 'eagleapi.history',
        name: 'EagleAPI requests',
        description: 'Your latest API requests with their status and time.',
        group: 'Tools',
        icon: Bird,
        tool: 'eagleapi',
        size: 'medium',
        settings: [LIMIT(20)],
        defaults: { limit: 6 },
        component: EagleHistoryWidget,
    },
    {
        type: 'tools.launcher',
        name: 'Tool shortcuts',
        description: 'Open any tool in one click.',
        group: 'Tools',
        icon: LayoutGrid,
        size: 'medium',
        component: ToolLauncherWidget,
    },
]

export function findWidget(type: string): WidgetDefinition | null {
    return WIDGETS.find((widget) => widget.type === type) ?? null
}

export function newWidgetId(): string {
    return `w${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function createWidget(definition: WidgetDefinition): DashboardWidget {
    return { id: newWidgetId(), type: definition.type, size: definition.size, settings: { ...definition.defaults } }
}

/** What a dashboard shows until the user changes it. */
export function defaultWidgets(): DashboardWidget[] {
    return [
        { id: 'runs-summary', type: 'runs.summary', size: 'full', settings: {} },
        { id: 'runs-active', type: 'runs.active', size: 'medium', settings: { limit: 8 } },
        { id: 'runs-recent', type: 'runs.recent', size: 'medium', settings: { limit: 8 } },
        { id: 'my-tasks', type: 'tasks.list', size: 'medium', settings: { filter: 'mine', limit: 8, quick_add: true } },
        { id: 'tool-shortcuts', type: 'tools.launcher', size: 'medium', settings: {} },
    ]
}
