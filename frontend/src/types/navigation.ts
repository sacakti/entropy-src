import {
    Activity,
    Blocks,
    KeyRound,
    LayoutDashboard,
    Server,
    ShieldCheck,
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
    | 'about'
    | 'settings'
    | 'preferences'
    | 'permissions'

export const navigation = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'plugins', label: 'Plugins', icon: Blocks },
    { id: 'workflows', label: 'Workflows', icon: Workflow },
    { id: 'vault', label: 'Vault', icon: KeyRound },
    { id: 'nodes', label: 'Nodes', icon: Server },
    { id: 'schedulers', label: 'Schedulers', icon: Activity },
    { id: 'administration', label: 'Administration', icon: ShieldCheck },
] satisfies {
    id: PageId
    label: string
    icon: typeof LayoutDashboard
}[]

const PAGE_IDS: readonly PageId[] = [
    'dashboard',
    'plugins',
    'workflows',
    'vault',
    'nodes',
    'schedulers',
    'administration',
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
