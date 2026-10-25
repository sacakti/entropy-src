/**
 * Tools shown in the Tools gallery.
 *
 * Adding a tool is adding an entry here: the gallery, search and the
 * opened view are built from this list. Components are loaded on demand,
 * so a tool's dependencies (Monaco for the compare tools) stay out of the
 * main bundle until the tool is opened.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import { Archive, Bird, GitBranch, GitCompareArrows, ListTodo, PackageCheck, type LucideIcon } from 'lucide-react'

export type ToolDefinition = {
    /** Stable identifier, safe to keep in URLs and preferences. */
    id: string
    name: string
    /** One line shown on the gallery card. */
    description: string
    icon: LucideIcon
    /** Extra words matched by the gallery search. */
    keywords?: string[]
    component: LazyExoticComponent<ComponentType> | ComponentType
}

export const TOOLS: ToolDefinition[] = [
    {
        id: 'clash',
        name: 'Clash',
        description: 'Compare text, files, and folders in one place.',
        icon: GitCompareArrows,
        keywords: ['text compare', 'file compare', 'folder compare', 'diff', 'upload', 'directory', 'json', 'yaml', 'sql'],
        component: lazy(() => import('./Clash')),
    },
    {
        id: 'eagleapi',
        name: 'EagleAPI',
        description: 'Send API requests with vault environments and polling',
        icon: Bird,
        keywords: ['api', 'http', 'rest', 'postman', 'request', 'oauth', 'certificate', 'poll'],
        component: lazy(() => import('./eagleapi/EagleApi')),
    },
    {
        id: 'tasks',
        name: 'Tasks',
        description: 'Track project work, assign members, discuss updates and set reminders.',
        icon: ListTodo,
        keywords: ['todo', 'kanban', 'board', 'comments', 'reminders', 'project'],
        component: lazy(() => import('./tasks/Tasks')),
    },
    {
        id: 'release-manager',
        name: 'Release Manager',
        description: 'Coordinate workflow releases, related tasks and environment promotions.',
        icon: PackageCheck,
        keywords: ['release', 'deployment', 'promotion', 'consolidation', 'environment', 'workflow'],
        component: lazy(() => import('./releases/ReleaseManager')),
    },
    {
        id: 'artifacts',
        name: 'Artifacts',
        description: 'Store release packages by upload or register files already on the Entropy server.',
        icon: Archive,
        keywords: ['packages', 'release', 'war', 'jar', 'zip', 'deployment', 'upload', 'path'],
        component: lazy(() => import('./artifacts/Artifacts')),
    },
    {
        id: 'git-repositories',
        name: 'Git repositories',
        description: 'Create private or project Git repositories and assign checkouts to workflows and plugins.',
        icon: GitBranch,
        keywords: ['git', 'source control', 'repository', 'checkout', 'workflow', 'plugin'],
        component: lazy(() => import('./git-repositories/GitRepositories')),
    },
]

export function findTool(id: string | null | undefined): ToolDefinition | null {
    if (!id) return null
    if (id === 'content-compare' || id === 'file-compare' || id === 'folder-compare') id = 'clash'
    return TOOLS.find((tool) => tool.id === id) ?? null
}

export function matchesTool(tool: ToolDefinition, query: string): boolean {
    const needle = query.trim().toLowerCase()
    if (!needle) return true

    return [tool.name, tool.description, ...(tool.keywords ?? [])].some((value) =>
        value.toLowerCase().includes(needle),
    )
}
