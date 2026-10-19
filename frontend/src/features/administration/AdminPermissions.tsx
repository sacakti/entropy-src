import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, LoaderCircle, LockKeyhole, Users } from 'lucide-react'

import { adminApi, type AdminModule, type AdminPermission, type AdminRole } from '../../api/admin.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { AdminPanel, Checklist, ChipList, SearchField } from './AdminPanel'
import { errorMessage, sameSet } from './format'
import { usePermissions } from './usePermissions'

type TypeFilter = 'all' | AdminPermission['type']

export default function AdminPermissions() {
    const { notify } = useFeedback()
    const permissions = usePermissions()
    const canAssign = permissions?.has('roles.permissions') ?? false

    const [modules, setModules] = useState<AdminModule[]>([])
    const [roles, setRoles] = useState<AdminRole[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [search, setSearch] = useState('')
    const [moduleFilter, setModuleFilter] = useState('')
    const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
    // With a role chosen, each permission gets a checkbox for that role.
    const [focusRole, setFocusRole] = useState('')
    const [busy, setBusy] = useState<string | null>(null)
    const [managing, setManaging] = useState<AdminPermission | null>(null)
    const searchRef = useRef<HTMLInputElement>(null)

    const load = useCallback(async () => {
        try {
            const [permissionList, roleList] = await Promise.all([adminApi.permissions(), adminApi.roles()])
            setModules(permissionList.modules)
            setRoles(roleList.items)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load permissions.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        // Load after mount; `load` only sets state once its requests settle.
        Promise.resolve().then(load)
    }, [load])

    useShortcuts(
        {
            'mod+f': () => {
                searchRef.current?.focus()
                searchRef.current?.select()
            },
        },
        managing === null,
    )

    const total = modules.reduce((sum, module) => sum + module.permissions.length, 0)
    const role = roles.find((item) => item.name === focusRole) ?? null

    const visible = useMemo(() => {
        const needle = search.trim().toLowerCase()

        return modules
            .filter((module) => !moduleFilter || module.name === moduleFilter)
            .map((module) => ({
                ...module,
                permissions: module.permissions.filter(
                    (permission) =>
                        (typeFilter === 'all' || permission.type === typeFilter) &&
                        (!needle ||
                            [permission.name, permission.description, ...permission.roles]
                                .join(' ')
                                .toLowerCase()
                                .includes(needle)),
                ),
            }))
            .filter((module) => module.permissions.length > 0)
    }, [moduleFilter, modules, search, typeFilter])

    const applyRoles = (permissionName: string, nextRoles: string[]) => {
        setModules((current) =>
            current.map((module) => ({
                ...module,
                permissions: module.permissions.map((permission) =>
                    permission.name === permissionName ? { ...permission, roles: nextRoles } : permission,
                ),
            })),
        )
        setRoles((current) =>
            current.map((item) => {
                const has = item.permissions.includes(permissionName)
                const wants = nextRoles.includes(item.name)
                if (has === wants) return item
                return {
                    ...item,
                    permissions: wants
                        ? [...item.permissions, permissionName]
                        : item.permissions.filter((name) => name !== permissionName),
                }
            }),
        )
    }

    const toggleForRole = async (permission: AdminPermission, grant: boolean) => {
        if (!role) return

        const nextRoles = grant
            ? [...permission.roles, role.name]
            : permission.roles.filter((name) => name !== role.name)

        setBusy(permission.name)

        try {
            const result = await adminApi.setPermissionRoles(permission.name, nextRoles)
            applyRoles(permission.name, result.roles)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to change the permission.'))
        } finally {
            setBusy(null)
        }
    }

    return (
        <div className="list-page admin-page">
            <AdminPanel
                title="Permissions"
                count={total}
                subtitle={`${modules.length} modules. Permissions are built into Entropy; grant them to roles.`}
                error={error}
                refreshing={refreshing || loading}
                onRefresh={() => {
                    setRefreshing(true)
                    void load()
                }}
                toolbar={
                    <>
                        <SearchField
                            inputRef={searchRef}
                            value={search}
                            onChange={setSearch}
                            placeholder="Search permissions or roles…"
                        />
                        <label className="list-filter">
                            <span>Module</span>
                            <select
                                className="entropy-select"
                                value={moduleFilter}
                                onChange={(event) => setModuleFilter(event.target.value)}
                            >
                                <option value="">All modules</option>
                                {modules.map((module) => (
                                    <option key={module.name} value={module.name}>
                                        {module.name}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="list-filter">
                            <span>Type</span>
                            <select
                                className="entropy-select"
                                value={typeFilter}
                                onChange={(event) => setTypeFilter(event.target.value as TypeFilter)}
                            >
                                <option value="all">All types</option>
                                <option value="read">Read</option>
                                <option value="write">Write</option>
                                <option value="execute">Execute</option>
                            </select>
                        </label>
                        {canAssign && (
                            <label className="list-filter">
                                <span>Edit role</span>
                                <select
                                    className="entropy-select"
                                    value={focusRole}
                                    onChange={(event) => setFocusRole(event.target.value)}
                                >
                                    <option value="">None</option>
                                    {roles
                                        .filter((item) => !item.is_builtin)
                                        .map((item) => (
                                            <option key={item.name} value={item.name}>
                                                {item.name} ({item.permissions.length})
                                            </option>
                                        ))}
                                </select>
                            </label>
                        )}
                    </>
                }
            >
                {role && (
                    <div className="entropy-alert admin-focus" role="status">
                        <Check size={15} />
                        <span>
                            Tick permissions to grant them to <strong>{role.name}</strong>; changes save
                            immediately. {role.permissions.length} of {total} granted.
                        </span>
                    </div>
                )}

                {loading && modules.length === 0 ? (
                    <p className="admin-muted">Loading permissions…</p>
                ) : visible.length === 0 ? (
                    <p className="admin-muted">No permissions match the filters.</p>
                ) : (
                    <div className="admin-modules">
                        {visible.map((module) => (
                            <section key={module.name} className="admin-module-card">
                                <header>
                                    <span className="list-name-icon" aria-hidden="true">
                                        <LockKeyhole size={15} />
                                    </span>
                                    <div>
                                        <h3>{module.name}</h3>
                                        {module.description && <p>{module.description}</p>}
                                    </div>
                                    <span className="entropy-count">{module.permissions.length}</span>
                                </header>

                                <ul>
                                    {module.permissions.map((permission) => (
                                        <li key={permission.name} className={role ? 'has-toggle' : undefined}>
                                            {role && (
                                                <span className="admin-permission-toggle">
                                                    {busy === permission.name ? (
                                                        <LoaderCircle size={15} className="entropy-spin" />
                                                    ) : (
                                                        <input
                                                            type="checkbox"
                                                            aria-label={`Grant ${permission.name} to ${role.name}`}
                                                            checked={permission.roles.includes(role.name)}
                                                            onChange={(event) =>
                                                                void toggleForRole(permission, event.target.checked)
                                                            }
                                                        />
                                                    )}
                                                </span>
                                            )}
                                            <div className="admin-permission-main">
                                                <strong>
                                                    <code>{permission.name}</code>
                                                    <span className={`admin-type is-${permission.type}`}>{permission.type}</span>
                                                </strong>
                                                {permission.description && <small>{permission.description}</small>}
                                            </div>
                                            <div className="admin-permission-roles">
                                                <ChipList values={permission.roles} max={4} tone="accent" empty="No roles" />
                                            </div>
                                            {canAssign && (
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-ghost entropy-button-sm"
                                                    onClick={() => setManaging(permission)}
                                                    title="Choose the roles that hold this permission"
                                                >
                                                    <Users size={14} />
                                                    Roles
                                                </button>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            </section>
                        ))}
                    </div>
                )}
            </AdminPanel>

            {managing && (
                <PermissionRolesDialog
                    permission={managing}
                    roles={roles}
                    onClose={() => setManaging(null)}
                    onSaved={(nextRoles) => {
                        applyRoles(managing.name, nextRoles)
                        setManaging(null)
                    }}
                />
            )}
        </div>
    )
}

function PermissionRolesDialog({
    permission,
    roles,
    onClose,
    onSaved,
}: {
    permission: AdminPermission
    roles: AdminRole[]
    onClose: () => void
    onSaved: (roles: string[]) => void
}) {
    const { notify } = useFeedback()
    const [selected, setSelected] = useState(permission.roles)
    const [saving, setSaving] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    const save = async () => {
        setSaving(true)
        setFormError(null)

        try {
            const result = await adminApi.setPermissionRoles(permission.name, selected)
            notify.success(`Roles updated for ${permission.name}.`)
            onSaved(result.roles)
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to update the roles.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={permission.name}
            subtitle={permission.description ?? 'Choose the roles that hold this permission.'}
            icon={<LockKeyhole size={18} />}
            onClose={onClose}
            className="admin-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => void save()}
                        disabled={saving || sameSet(selected, permission.roles)}
                    >
                        {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Check size={15} />}
                        Save roles
                    </button>
                </>
            }
        >
            <Checklist
                items={roles.map((role) => ({
                    value: role.name,
                    detail: role.is_builtin ? 'Built-in; always has every permission' : role.description,
                    locked: role.is_builtin,
                }))}
                selected={selected}
                onChange={setSelected}
                placeholder="Search roles"
            />

            {formError && (
                <div className="entropy-alert entropy-alert-error admin-form-error" role="alert">
                    <span>{formError}</span>
                </div>
            )}
        </Dialog>
    )
}
