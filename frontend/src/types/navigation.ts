import {
    Activity,
    ArrowUpCircle,
    BadgeCheck,
    Blocks,
    KeyRound,
    LayoutDashboard,
    LockKeyhole,
    PlayCircle,
    Server,
    ShieldCheck,
    UserRound,
    UsersRound,
    Workflow,
} from 'lucide-react'

export type PageId =
    | 'dashboard'
    | 'plugins'
    | 'workflows'
    | 'runs'
    | 'vault'
    | 'nodes'
    | 'schedulers'
    | 'administration'
    | 'admin-users'
    | 'admin-groups'
    | 'admin-roles'
    | 'admin-permissions'
    | 'admin-system'
    | 'about'
    | 'settings'
    | 'preferences'
    | 'permissions'

export const navigation: NavigationItem[] = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'plugins', label: 'Plugins', icon: Blocks },
    { id: 'workflows', label: 'Workflows', icon: Workflow },
    { id: 'runs', label: 'Runs', icon: PlayCircle },
    { id: 'vault', label: 'Vault', icon: KeyRound },
    { id: 'nodes', label: 'Nodes', icon: Server },
    { id: 'schedulers', label: 'Schedulers', icon: Activity },
    {
        id: 'administration',
        label: 'Administration',
        icon: ShieldCheck,
        children: [
            { id: 'admin-users', label: 'Users', icon: UserRound },
            { id: 'admin-groups', label: 'Groups', icon: UsersRound },
            { id: 'admin-roles', label: 'Roles', icon: BadgeCheck },
            { id: 'admin-permissions', label: 'Permissions', icon: LockKeyhole },
            { id: 'admin-system', label: 'System', icon: ArrowUpCircle },
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
    'workflows',
    'runs',
    'vault',
    'nodes',
    'schedulers',
    'administration',
    'admin-users',
    'admin-groups',
    'admin-roles',
    'admin-permissions',
    'admin-system',
    'about',
    'settings',
    'preferences',
    'permissions',
]

/** Page named by a location hash such as `#/vault`, if any. */
export function pageFromHash(hash: string): PageId | null {
    // `#/runs/42` is the live screen of run 42, under the Runs page.
    const id = hash.replace(/^#\/?/, '').split('/')[0]
    return (PAGE_IDS as readonly string[]).includes(id) ? (id as PageId) : null
}

/** Pages the API refuses without one of these permissions. */
export const PAGE_PERMISSIONS: Partial<Record<PageId, string[]>> = {
    dashboard: ['workflows.list'],
    plugins: ['plugins.list'],
    workflows: ['workflows.list'],
    runs: ['workflows.list'],
    nodes: ['nodes.list'],
    schedulers: ['schedules.list'],
    administration: ['users.read', 'groups.read', 'roles.read'],
    'admin-users': ['users.read'],
    'admin-groups': ['groups.read'],
    'admin-roles': ['roles.read'],
    'admin-permissions': ['roles.read'],
    'admin-system': ['upgrade.entropy'],
}
