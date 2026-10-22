import {
    Activity,
    ArrowUpCircle,
    BadgeCheck,
    Blocks,
    FolderKanban,
    KeyRound,
    LayoutDashboard,
    Package,
    PlayCircle,
    Server,
    ShieldCheck,
    SlidersHorizontal,
    UserRound,
    UsersRound,
    Workflow,
    Wrench,
} from 'lucide-react'

export type PageId =
    | 'dashboard'
    | 'plugins'
    | 'extensions'
    | 'workflows'
    | 'runs'
    | 'vault'
    | 'nodes'
    | 'schedulers'
    | 'tools'
    | 'administration'
    | 'admin-projects'
    | 'admin-users'
    | 'admin-groups'
    | 'admin-roles'
    | 'admin-settings'
    | 'admin-system'
    | 'about'
    | 'settings'
    | 'preferences'
    | 'permissions'

export const navigation: NavigationItem[] = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'plugins', label: 'Plugins', icon: Blocks },
    { id: 'extensions', label: 'Extensions', icon: Package },
    { id: 'workflows', label: 'Workflows', icon: Workflow },
    { id: 'runs', label: 'Runs', icon: PlayCircle },
    { id: 'vault', label: 'Vault', icon: KeyRound },
    { id: 'schedulers', label: 'Schedulers', icon: Activity },
    { id: 'tools', label: 'Tools', icon: Wrench },
    {
        // Managing Entropy itself; shown only to those who may manage part of it.
        id: 'administration',
        label: 'Administration',
        icon: ShieldCheck,
        children: [
            { id: 'admin-projects', label: 'Projects', icon: FolderKanban },
            { id: 'admin-users', label: 'Users', icon: UserRound },
            { id: 'admin-groups', label: 'Groups', icon: UsersRound },
            { id: 'admin-roles', label: 'Roles', icon: BadgeCheck },
            { id: 'nodes', label: 'Nodes', icon: Server },
            { id: 'admin-settings', label: 'Settings', icon: SlidersHorizontal },
            { id: 'admin-system', label: 'Upgrade', icon: ArrowUpCircle },
        ],
    },
]

export interface NavigationItem {
    id: PageId
    label: string
    icon: typeof LayoutDashboard
    children?: NavigationItem[]
}

/** The navigation entry a page sits under, for sub-pages such as Users. */
export function parentPage(page: PageId): NavigationItem | null {
    return navigation.find((item) => item.children?.some((child) => child.id === page)) ?? null
}

const PAGE_IDS: readonly PageId[] = [
    'dashboard',
    'plugins',
    'extensions',
    'workflows',
    'runs',
    'vault',
    'nodes',
    'schedulers',
    'tools',
    'administration',
    'admin-projects',
    'admin-users',
    'admin-groups',
    'admin-roles',
    'admin-settings',
    'admin-system',
    'about',
    'settings',
    'preferences',
    'permissions',
]

/** Page named by a location hash such as `#/vault`, if any. */
export function pageFromHash(hash: string): PageId | null {
    // `#/runs/42` is the live screen of run 42, under the Runs page.
    // `#/runs?tab=all` is the Runs page with a tab chosen.
    const id = hash.replace(/^#\/?/, '').split(/[/?]/)[0]
    return (PAGE_IDS as readonly string[]).includes(id) ? (id as PageId) : null
}

/** Pages the API refuses without one of these permissions. */
export const PAGE_PERMISSIONS: Partial<Record<PageId, string[]>> = {
    dashboard: ['workflows.read'],
    plugins: ['plugins.read'],
    extensions: ['extensions.list'],
    workflows: ['workflows.read'],
    runs: ['workflows.read'],
    nodes: ['nodes.list'],
    schedulers: ['schedules.list'],
    administration: [
        'users.read',
        'groups.read',
        'roles.read',
        'projects.manage',
        'projects.members',
        'nodes.list',
        'system.settings',
        'upgrade.entropy',
    ],
    // Project maintainers (projects.members in the current project) manage members here.
    'admin-projects': ['projects.manage', 'projects.read', 'projects.members'],
    'admin-users': ['users.read'],
    'admin-groups': ['groups.read'],
    'admin-roles': ['roles.read'],
    'admin-settings': ['system.settings'],
    'admin-system': ['upgrade.entropy'],
}

/** Whether `permissions` open a page (unknown permissions: assume yes). */
export function canOpen(page: PageId, permissions: Set<string> | null): boolean {
    const required = PAGE_PERMISSIONS[page]
    return !required || !permissions || required.some((permission) => permissions.has(permission))
}
