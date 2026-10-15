import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    Check,
    LoaderCircle,
    RefreshCw,
    Search,
    ShieldCheck,
} from 'lucide-react'

import { getCurrentUser } from '../../services/auth'

interface PermissionGroup {
    name: string
    permissions: string[]
}

const GROUP_ORDER = [
    'auth',
    'users',
    'roles',
    'groups',
    'vault',
    'workflows',
    'plugins',
    'extensions',
    'generate',
    'migrate',
    'upgrade',
]

function formatResource(resource: string): string {
    const names: Record<string, string> = {
        auth: 'Authentication',
        users: 'Users',
        roles: 'Roles',
        groups: 'Groups',
        vault: 'Vault',
        workflows: 'Workflows',
        plugins: 'Plugins',
        extensions: 'Extensions',
        generate: 'Generation',
        migrate: 'Database',
        upgrade: 'Upgrade',
    }

    return names[resource] ?? resource.charAt(0).toUpperCase() + resource.slice(1)
}

function formatPermission(permission: string): string {
    const action = permission.split('.').slice(1).join('.')

    return action
        .split('.')
        .map((part) =>
            part
                .replace(/[-_]/g, ' ')
                .replace(/\b\w/g, (character) => character.toUpperCase()),
        )
        .join(' / ')
}

function groupPermissions(permissions: string[]): PermissionGroup[] {
    const groups = new Map<string, string[]>()

    for (const permission of permissions) {
        const separator = permission.indexOf('.')
        const resource =
            separator === -1 ? 'other' : permission.slice(0, separator)

        const current = groups.get(resource) ?? []
        current.push(permission)
        groups.set(resource, current)
    }

    return Array.from(groups.entries())
        .map(([resource, items]) => ({
            name: resource,
            permissions: items.sort((a, b) => a.localeCompare(b)),
        }))
        .sort((a, b) => {
            const aIndex = GROUP_ORDER.indexOf(a.name)
            const bIndex = GROUP_ORDER.indexOf(b.name)

            const aOrder = aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex
            const bOrder = bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex

            return aOrder - bOrder || a.name.localeCompare(b.name)
        })
}

function Permissions() {
    const [permissions, setPermissions] = useState<string[]>([])
    const [search, setSearch] = useState('')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    const loadPermissions = useCallback(async () => {
        setLoading(true)
        setError('')

        try {
            const currentUser = await getCurrentUser()
            const uniquePermissions = [...new Set(currentUser.permissions)]

            setPermissions(uniquePermissions.sort((a, b) => a.localeCompare(b)))
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : 'Unable to load permissions.',
            )
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void loadPermissions()
    }, [loadPermissions])

    const filteredPermissions = useMemo(() => {
        const query = search.trim().toLowerCase()

        if (!query) {
            return permissions
        }

        return permissions.filter((permission) =>
            permission.toLowerCase().includes(query),
        )
    }, [permissions, search])

    const groups = useMemo(
        () => groupPermissions(filteredPermissions),
        [filteredPermissions],
    )

    return (
        // <section className="content-panel permissions-page">
        <section className="permissions-page">
            <header className="permissions-header">
                <div className="permissions-heading">
                    <span className="permissions-heading-icon">
                        <ShieldCheck size={23} />
                    </span>

                    <div>
                        <p className="permissions-eyebrow">
                            ACCESS CONTROL
                        </p>
                        <h2>Permissions</h2>
                        <p className="permissions-description">
                            Review the permissions assigned to your account.
                        </p>
                    </div>
                </div>

                {/* <button
                    type="button"
                    className="entropy-button-secondary"
                    onClick={() => void loadPermissions()}
                    disabled={loading}
                    aria-label="Refresh permissions"
                    title="Refresh permissions"
                >
                    <RefreshCw
                        size={16}
                        className={loading ? 'permissions-spinning' : ''}
                    />
                    <span>Refresh</span>
                </button> */}
            </header>

            {error ? (
                <div className="permissions-message permissions-error" role="alert">
                    <AlertCircle size={19} />
                    <div className="permissions-message-content">
                        <strong>Unable to load permissions</strong>
                        <p>{error}</p>
                        <button
                            type="button"
                            className="entropy-button-secondary"
                            onClick={() => void loadPermissions()}
                            disabled={loading}
                        >
                            Try again
                        </button>
                    </div>
                </div>
            ) : loading ? (
                <div className="permissions-message permissions-loading" role="status">
                    <LoaderCircle
                        size={22}
                        className="permissions-spinning"
                    />
                    <span>Loading your permissions...</span>
                </div>
            ) : (
                <>
                    <div className="permissions-summary">
                        <div className="permissions-summary-card">
                            <span className="permissions-summary-label">
                                Assigned permissions
                            </span>
                            <strong>{permissions.length}</strong>
                            <span className="permissions-summary-caption">
                                Unique permissions
                            </span>
                        </div>

                        <div className="permissions-summary-card">
                            <span className="permissions-summary-label">
                                Resources
                            </span>
                            <strong>{groupPermissions(permissions).length}</strong>
                            <span className="permissions-summary-caption">
                                Resource categories
                            </span>
                        </div>

                        <div className="permissions-summary-card">
                            <span className="permissions-summary-label">
                                Search results
                            </span>
                            <strong>{filteredPermissions.length}</strong>
                            <span className="permissions-summary-caption">
                                Matching permissions
                            </span>
                        </div>
                    </div>

                    <div className="permissions-toolbar">
                        <label
                            className="permissions-search"
                            htmlFor="permissions-search-input"
                        >
                            <Search size={17} />
                            <input
                                id="permissions-search-input"
                                type="search"
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search permissions..."
                            />
                        </label>

                        <span className="permissions-result-count">
                            {filteredPermissions.length}{' '}
                            {filteredPermissions.length === 1
                                ? 'permission'
                                : 'permissions'}
                        </span>
                    </div>

                    {permissions.length === 0 ? (
                        <div className="permissions-empty">
                            <ShieldCheck size={28} />
                            <h3>No permissions assigned</h3>
                            <p>
                                Your account currently has no permissions returned
                                by the authentication service.
                            </p>
                        </div>
                    ) : groups.length === 0 ? (
                        <div className="permissions-empty">
                            <Search size={26} />
                            <h3>No matching permissions</h3>
                            <p>
                                Try another search term or clear your search.
                            </p>
                            <button
                                type="button"
                                className="permissions-retry"
                                onClick={() => setSearch('')}
                            >
                                Clear search
                            </button>
                        </div>
                    ) : (
                        <div className="permissions-groups">
                            {groups.map((group) => (
                                <section
                                    className="permissions-group"
                                    key={group.name}
                                >
                                    <header className="permissions-group-header">
                                        <div>
                                            <h3>{formatResource(group.name)}</h3>
                                            <span className="permissions-group-key">
                                                {group.name}
                                            </span>
                                        </div>

                                        <span className="permissions-group-count">
                                            {group.permissions.length}
                                        </span>
                                    </header>

                                    <div className="permissions-list">
                                        {group.permissions.map((permission) => (
                                            <div
                                                className="permissions-item"
                                                key={permission}
                                            >
                                                <span className="permissions-item-check">
                                                    <Check size={14} />
                                                </span>

                                                <span className="permissions-item-name">
                                                    {formatPermission(permission)}
                                                </span>

                                                <code>{permission}</code>
                                            </div>
                                        ))}
                                    </div>
                                </section>
                            ))}
                        </div>
                    )}
                </>
            )}
        </section>
    )
}

export default Permissions
