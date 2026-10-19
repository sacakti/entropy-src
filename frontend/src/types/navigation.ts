import {
    Activity,
    BadgeCheck,
    Blocks,
    KeyRound,
    LayoutDashboard,
    LockKeyhole,
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
    | 'vault'
    | 'nodes'
    | 'schedulers'
    | 'administration'
    | 'admin-users'
    | 'admin-groups'
    | 'admin-roles'
    | 'admin-permissions'
    | 'about'
    | 'settings'
    | 'preferences'
    | 'permissions'

export const navigation: NavigationItem[] = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'plugins', label: 'Plugins', icon: Blocks },
    { id: 'workflows', label: 'Workflows', icon: Workflow },
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
    'vault',
    'nodes',
    'schedulers',
    'administration',
    'admin-users',
    'admin-groups',
    'admin-roles',
    'admin-permissions',
    'about',
    'settings',
    'preferences',
    'permissions',
]

/** Page named by a location hash such as `#/vault`, if any. */
export function pageFromHash(hash: string): PageId | null {
    const id = hash.replace(/^#\/?/, '')
    return (PAGE_IDS as readonly string[]).includes(id) ? (id as PageId) : null
}

/** Pages the API refuses without one of these permissions. */
export const PAGE_PERMISSIONS: Partial<Record<PageId, string[]>> = {
    dashboard: ['workflows.list'],
    plugins: ['plugins.list'],
    workflows: ['workflows.list'],
    administration: ['users.read', 'groups.read', 'roles.read'],
    'admin-users': ['users.read'],
    'admin-groups': ['groups.read'],
    'admin-roles': ['roles.read'],
    'admin-permissions': ['roles.read'],
}
