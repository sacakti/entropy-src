/**
 * Tools shown in the Tools gallery.
 *
 * Adding a tool is adding an entry here: the gallery, search and the
 * opened view are built from this list. Components are loaded on demand,
 * so a tool's dependencies (Monaco for the compare tools) stay out of the
 * main bundle until the tool is opened.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import { Bird, FileDiff, FolderTree, GitCompareArrows, type LucideIcon } from 'lucide-react'

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
        id: 'content-compare',
        name: 'Text compare',
        description: 'Paste two texts and see what changed, side by side or inline.',
        icon: GitCompareArrows,
        keywords: ['diff', 'content', 'paste', 'json', 'yaml', 'sql'],
        component: lazy(() => import('./ContentCompare')),
    },
    {
        id: 'file-compare',
        name: 'File compare',
        description: 'Pick or drop two text files and compare their contents.',
        icon: FileDiff,
        keywords: ['diff', 'upload', 'drop'],
        component: lazy(() => import('./FileCompare')),
    },
    {
        id: 'folder-compare',
        name: 'Folder compare',
        description: 'Compare two folders file by file: identical, changed or missing.',
        icon: FolderTree,
        keywords: ['diff', 'directory', 'tree', 'hash', 'checksum'],
        component: lazy(() => import('./FolderCompare')),
    },
    {
        id: 'eagleapi',
        name: 'EagleAPI',
        description: 'Send API requests with vault environments and polling',
        icon: Bird,
        keywords: ['api', 'http', 'rest', 'postman', 'request', 'oauth', 'certificate', 'poll'],
        component: lazy(() => import('./eagleapi/EagleApi')),
    },
]

export function findTool(id: string | null | undefined): ToolDefinition | null {
    if (!id) return null
    return TOOLS.find((tool) => tool.id === id) ?? null
}

export function matchesTool(tool: ToolDefinition, query: string): boolean {
    const needle = query.trim().toLowerCase()
    if (!needle) return true

    return [tool.name, tool.description, ...(tool.keywords ?? [])].some((value) =>
        value.toLowerCase().includes(needle),
    )
}
