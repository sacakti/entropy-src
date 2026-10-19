import { useEffect, useState } from 'react'
import { AlertCircle, ArrowRight, BadgeCheck, LockKeyhole, UserRound, UsersRound } from 'lucide-react'

import { adminApi, type AdminSummary } from '../../api/admin.api'
import type { PageId } from '../../types/navigation'
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
        page: 'admin-users',
        title: 'Users',
        description: 'Create accounts, reset passwords, enable or disable access, assign roles and groups.',
        icon: UserRound,
        stat: (summary) => `${summary.users} users · ${summary.active_users} active`,
    },
    {
        page: 'admin-groups',
        title: 'Groups',
        description: 'Collect users into groups so they share the same roles.',
        icon: UsersRound,
        stat: (summary) => `${summary.groups} groups`,
    },
    {
        page: 'admin-roles',
        title: 'Roles',
        description: 'Define named sets of permissions to give to users and groups.',
        icon: BadgeCheck,
        stat: (summary) => `${summary.roles} roles`,
    },
    {
        page: 'admin-permissions',
        title: 'Permissions',
        description: 'Browse every Entropy permission by module and choose which roles hold it.',
        icon: LockKeyhole,
        stat: (summary) => `${summary.permissions} permissions · ${summary.modules} modules`,
    },
]

export default function Administration({ onNavigate }: { onNavigate: (page: PageId) => void }) {
    const [summary, setSummary] = useState<AdminSummary | null>(null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true

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
    }, [])

    return (
        <div className="list-page admin-page">
            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            <div className="admin-overview">
                {SECTIONS.map(({ page, title, description, icon: Icon, stat }) => (
                    <button key={page} type="button" className="admin-overview-card" onClick={() => onNavigate(page)}>
                        <span className="admin-overview-icon" aria-hidden="true">
                            <Icon size={20} />
                        </span>
                        <span className="admin-overview-copy">
                            <strong>{title}</strong>
                            <span>{description}</span>
                        </span>
                        <span className="admin-overview-stat">{summary ? stat(summary) : '…'}</span>
                        <ArrowRight size={16} className="admin-overview-arrow" aria-hidden="true" />
                    </button>
                ))}
            </div>

            {summary && <AdminCharts summary={summary} />}
        </div>
    )
}
