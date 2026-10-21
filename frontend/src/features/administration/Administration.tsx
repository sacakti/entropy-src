import { useEffect, useState } from 'react'
import {
    AlertCircle,
    ArrowRight,
    ArrowUpCircle,
    BadgeCheck,
    FolderKanban,
    Server,
    SlidersHorizontal,
    UserRound,
    UsersRound,
} from 'lucide-react'

import { adminApi, type AdminSummary } from '../../api/admin.api'
import { canOpen, type PageId } from '../../types/navigation'
import AdminCharts from './AdminCharts'
import { errorMessage } from './format'

const SECTIONS: {
    page: PageId
    title: string
    description: string
    icon: typeof UserRound
    stat: (summary: AdminSummary) => string
}[] = [
    {
        page: 'admin-projects',
        title: 'Projects',
        description: 'Group workflows, schedules and runs into projects and choose who works in each.',
        icon: FolderKanban,
        stat: () => 'Members and nodes',
    },
    {
        page: 'admin-users',
        title: 'Users',
        description: 'Create accounts, reset passwords, enable or disable access, give roles and projects.',
        icon: UserRound,
        stat: (summary) => `${summary.users} users · ${summary.active_users} active`,
    },
    {
        page: 'admin-groups',
        title: 'Groups',
        description: 'Collect users into groups so they share the same roles and projects.',
        icon: UsersRound,
        stat: (summary) => `${summary.groups} groups`,
    },
    {
        page: 'admin-roles',
        title: 'Roles',
        description: 'Global roles apply everywhere; project roles apply in the projects they are given in.',
        icon: BadgeCheck,
        stat: (summary) => `${summary.roles} roles`,
    },
    {
        page: 'nodes',
        title: 'Nodes',
        description: 'Add, set up and remove execution nodes; share them or assign them to projects.',
        icon: Server,
        stat: () => 'Runners',
    },
    {
        page: 'admin-settings',
        title: 'Settings',
        description: 'E-mail (SMTP), sign-in with LDAP or single sign-on, data retention and purging.',
        icon: SlidersHorizontal,
        stat: () => 'E-mail, sign-in, data',
    },
    {
        page: 'admin-system',
        title: 'Upgrade',
        description: 'See how Entropy is installed, upgrade it from a release package, or roll back.',
        icon: ArrowUpCircle,
        stat: () => 'Version and upgrades',
    },
]

export default function Administration({
    onNavigate,
    permissions,
}: {
    onNavigate: (page: PageId) => void
    permissions: Set<string> | null
}) {
    const [summary, setSummary] = useState<AdminSummary | null>(null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true

        // The summary needs users.read; other administrators just see the sections.
        if (permissions && !permissions.has('users.read')) return
        adminApi
            .summary()
            .then((result) => {
                if (active) setSummary(result)
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load the administration summary.'))
            })

        return () => {
            active = false
        }
    }, [permissions])

    return (
        <div className="list-page admin-page">
            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            <div className="admin-overview">
                {SECTIONS.filter((section) => canOpen(section.page, permissions)).map(
                    ({ page, title, description, icon: Icon, stat }) => (
                    <button key={page} type="button" className="admin-overview-card" onClick={() => onNavigate(page)}>
                        <span className="admin-overview-icon" aria-hidden="true">
                            <Icon size={20} />
                        </span>
                        <span className="admin-overview-copy">
                            <strong>{title}</strong>
                            <span>{description}</span>
                        </span>
                        <span className="admin-overview-stat">{summary ? stat(summary) : ''}</span>
                        <ArrowRight size={16} className="admin-overview-arrow" aria-hidden="true" />
                    </button>
                    ),
                )}
            </div>

            {summary && <AdminCharts summary={summary} />}
        </div>
    )
}
