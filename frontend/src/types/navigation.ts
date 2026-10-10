import {
    Activity,
    Blocks,
    Info,
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

export const pageDescriptions: Record<PageId, string> = {
    dashboard: 'Monitor activity across your deployment workspace.',
    plugins: 'Develop and manage Entropy plugins.',
    workflows: 'Create, validate, and manage deployment workflows.',
    vault: 'Manage your vaults and their configuration.',
    nodes: 'Entropy execution infrastructure.',
    schedulers: 'Manage scheduled workflow executions.',
    administration: 'Manage Entropy users and access.',
    about: 'Entropy deployment management platform.',
    settings: 'Manage your account settings and security.',
    preferences: 'Personalize your Entropy workspace.',
    permissions: 'Review your account permissions.',
}
