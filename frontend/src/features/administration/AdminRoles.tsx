import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { BadgeCheck, Check, LoaderCircle, Lock, Pencil, Plus, Search, Trash2 } from 'lucide-react'

import { adminApi, type AdminModule, type AdminRole } from '../../api/admin.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import { AdminPanel, ChipList, EmptyRow, SearchField, Tabs } from './AdminPanel'
import { errorMessage, sameSet } from './format'
import { usePermissions } from './usePermissions'

export default function AdminRoles() {
    const { notify, modal } = useFeedback()
    const permissions = usePermissions()
    const can = (permission: string) => permissions?.has(permission) ?? false

    const [roles, setRoles] = useState<AdminRole[]>([])
    const [modules, setModules] = useState<AdminModule[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [search, setSearch] = useState('')
    const [editing, setEditing] = useState<AdminRole | 'new' | null>(() =>
        consumeCreateIntent('role') ? 'new' : null,
    )
    const [deleting, setDeleting] = useState<string | null>(null)
    const searchRef = useRef<HTMLInputElement>(null)

    const load = useCallback(async () => {
        try {
            const [roleList, permissionList] = await Promise.all([adminApi.roles(), adminApi.permissions()])
            setRoles(roleList.items)
            setModules(permissionList.modules)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load roles.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        // Load after mount; `load` only sets state once its requests settle.
        Promise.resolve().then(load)
    }, [load])

    const totalPermissions = modules.reduce((sum, module) => sum + module.permissions.length, 0)

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase()

        return needle
            ? roles.filter((role) =>
                  [role.name, role.description, ...role.permissions].join(' ').toLowerCase().includes(needle),
              )
            : roles
    }, [roles, search])

    const remove = async (role: AdminRole) => {
        const holders = role.users.length + role.groups.length
        const confirmed = await modal.confirm({
            title: `Delete role ${role.name}?`,
            message: holders
                ? `${role.users.length} user(s) and ${role.groups.length} group(s) lose its ${role.permissions.length} permissions. This cannot be undone.`
                : 'This cannot be undone.',
            confirmText: 'Delete role',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setDeleting(role.name)

        try {
            await adminApi.deleteRole(role.name)
            setRoles((current) => current.filter((item) => item.id !== role.id))
            notify.success(`Role '${role.name}' deleted.`)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the role.'))
        } finally {
            setDeleting(null)
        }
    }

    const openCreate = () => {
        if (can('roles.create')) setEditing('new')
    }

    useCreateIntent('role', () => setEditing('new'))

    useShortcuts(
        {
            'mod+n': openCreate,
            'alt+n': openCreate,
            'mod+f': () => {
                searchRef.current?.focus()
                searchRef.current?.select()
            },
        },
        editing === null,
    )

    return (
        <div className="list-page admin-page">
            <AdminPanel
                title="Roles"
                count={roles.length}
                subtitle="A role is a named set of permissions, given to users directly or through groups."
                error={error}
                refreshing={refreshing || loading}
                onRefresh={() => {
                    setRefreshing(true)
                    void load()
                }}
                actions={
                    can('roles.create') && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon"
                            aria-label="Create role"
                            title="Create role (Ctrl+N)"
                            onClick={openCreate}
                        >
                            <Plus size={20} />
                        </button>
                    )
                }
                toolbar={
                    <SearchField
                        inputRef={searchRef}
                        value={search}
                        onChange={setSearch}
                        placeholder="Search roles or permissions…"
                    />
                }
            >
                <div className="list-table-wrap">
                    <table className="list-table">
                        <thead>
                            <tr>
                                <th>Role</th>
                                <th>Permissions</th>
                                <th>Users</th>
                                <th>Groups</th>
                                <th className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && roles.length === 0 ? (
                                <EmptyRow colSpan={5} title="Loading roles…" text="Fetching roles." />
                            ) : filtered.length === 0 ? (
                                <EmptyRow colSpan={5} title="No roles match" text="Try a different search." />
                            ) : (
                                filtered.map((role) => (
                                    <tr key={role.id}>
                                        <td>
                                            <div className="list-name">
                                                <span className="list-name-icon" aria-hidden="true">
                                                    {role.is_builtin ? <Lock size={15} /> : <BadgeCheck size={16} />}
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>
                                                        {role.name}
                                                        {role.is_builtin && <span className="admin-badge">Built-in</span>}
                                                    </strong>
                                                    <span>{role.description || 'No description'}</span>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <div className="admin-meter" title={`${role.permissions.length} of ${totalPermissions}`}>
                                                <span>
                                                    <span
                                                        style={{
                                                            width: `${totalPermissions ? (role.permissions.length / totalPermissions) * 100 : 0}%`,
                                                        }}
                                                    />
                                                </span>
                                                <small>
                                                    {role.permissions.length}/{totalPermissions}
                                                </small>
                                            </div>
                                        </td>
                                        <td>
                                            <ChipList values={role.users} empty="None" />
                                        </td>
                                        <td>
                                            <ChipList values={role.groups} empty="None" />
                                        </td>
                                        <td>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`${role.is_builtin ? 'View' : 'Edit'} ${role.name}`}
                                                    title={role.is_builtin ? 'View' : 'Edit'}
                                                    onClick={() => setEditing(role)}
                                                >
                                                    {role.is_builtin ? <Search size={15} /> : <Pencil size={15} />}
                                                </button>
                                                {can('roles.delete') && (
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                        aria-label={`Delete ${role.name}`}
                                                        title={role.is_builtin ? 'The built-in role cannot be deleted' : 'Delete'}
                                                        disabled={role.is_builtin || deleting === role.name}
                                                        onClick={() => void remove(role)}
                                                    >
                                                        {deleting === role.name ? (
                                                            <LoaderCircle size={15} className="entropy-spin" />
                                                        ) : (
                                                            <Trash2 size={15} />
                                                        )}
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </AdminPanel>

            {editing && (
                <RoleDialog
                    role={editing === 'new' ? null : editing}
                    modules={modules}
                    can={can}
                    onClose={() => setEditing(null)}
                    onSaved={() => {
                        setEditing(null)
                        void load()
                    }}
                />
            )}
        </div>
    )
}

type RoleTab = 'details' | 'permissions' | 'assigned'

function RoleDialog({
    role,
    modules,
    can,
    onClose,
    onSaved,
}: {
    role: AdminRole | null
    modules: AdminModule[]
    can: (permission: string) => boolean
    onClose: () => void
    onSaved: () => void
}) {
    const { notify } = useFeedback()
    const creating = role === null
    const locked = role?.is_builtin ?? false

    const [tab, setTab] = useState<RoleTab>('details')
    const [name, setName] = useState(role?.name ?? '')
    const [description, setDescription] = useState(role?.description ?? '')
    const [granted, setGranted] = useState<string[]>(role?.permissions ?? [])
    const [saving, setSaving] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    const canDetails = !locked && (creating ? can('roles.create') : can('roles.modify'))
    const canPermissions = !locked && can('roles.permissions')

    const detailsDirty =
        creating || name.trim() !== role.name || description.trim() !== (role.description ?? '')
    const permissionsDirty = !sameSet(granted, role?.permissions ?? [])

    const save = async (event?: FormEvent) => {
        event?.preventDefault()

        if (saving || locked) return

        setSaving(true)
        setFormError(null)

        try {
            if (!name.trim()) throw new Error('Enter a role name.')

            let current = name.trim()

            if (creating) {
                await adminApi.createRole({ name: current, description: description.trim() || null })
            } else if (detailsDirty) {
                current = (await adminApi.updateRole(role.name, { name: current, description: description.trim() })).name
            }

            if (canPermissions && permissionsDirty) await adminApi.setRolePermissions(current, granted)

            notify.success(`Role '${current}' ${creating ? 'created' : 'updated'}.`)
            onSaved()
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to save the role.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={creating ? 'Create role' : locked ? `${role.name} (built-in)` : `Edit ${role.name}`}
            subtitle={
                locked
                    ? 'The built-in administrator role always has every permission and cannot be changed.'
                    : 'Choose what holders of this role may do.'
            }
            icon={locked ? <Lock size={18} /> : <BadgeCheck size={18} />}
            onClose={onClose}
            className="admin-dialog admin-dialog-wide"
            footer={
                locked ? (
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Close
                    </button>
                ) : (
                    <>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Cancel
                        </button>
                        <button
                            type="submit"
                            form="admin-role-form"
                            className="entropy-button entropy-button-primary"
                            disabled={saving || !(detailsDirty || permissionsDirty)}
                        >
                            {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Check size={15} />}
                            {creating ? 'Create role' : 'Save changes'}
                        </button>
                    </>
                )
            }
        >
            <Tabs
                tabs={[
                    { id: 'details' as const, label: 'Details' },
                    { id: 'permissions' as const, label: 'Permissions', count: granted.length },
                    ...(creating
                        ? []
                        : [{ id: 'assigned' as const, label: 'Assigned to', count: role.users.length + role.groups.length }]),
                ]}
                active={tab}
                onChange={setTab}
            />

            <form id="admin-role-form" className="admin-form" onSubmit={save}>
                {tab === 'details' && (
                    <div className="admin-form-grid">
                        <label className="admin-field admin-field-wide">
                            <span>Name</span>
                            <input
                                value={name}
                                onChange={(event) => setName(event.target.value)}
                                placeholder="e.g. release-manager"
                                disabled={!canDetails}
                                maxLength={100}
                                spellCheck={false}
                                required
                            />
                        </label>
                        <label className="admin-field admin-field-wide">
                            <span>Description</span>
                            <textarea
                                value={description}
                                onChange={(event) => setDescription(event.target.value)}
                                placeholder="What is this role for?"
                                disabled={!canDetails}
                                maxLength={500}
                                rows={3}
                            />
                        </label>
                    </div>
                )}

                {tab === 'permissions' && (
                    <PermissionPicker
                        modules={modules}
                        selected={granted}
                        onChange={setGranted}
                        disabled={!canPermissions}
                    />
                )}

                {tab === 'assigned' && role && (
                    <div className="admin-assigned">
                        <section>
                            <h3>Users ({role.users.length})</h3>
                            <ChipList values={role.users} max={50} empty="No users hold this role directly." />
                        </section>
                        <section>
                            <h3>Groups ({role.groups.length})</h3>
                            <ChipList values={role.groups} max={50} empty="No groups grant this role." />
                        </section>
                        <p className="admin-muted">
                            Assign roles from Administration › Users or › Groups.
                        </p>
                    </div>
                )}
            </form>

            {formError && (
                <div className="entropy-alert entropy-alert-error admin-form-error" role="alert">
                    <span>{formError}</span>
                </div>
            )}
        </Dialog>
    )
}

/** Permissions grouped by module, each module with a select-all box. */
function PermissionPicker({
    modules,
    selected,
    onChange,
    disabled,
}: {
    modules: AdminModule[]
    selected: string[]
    onChange: (selected: string[]) => void
    disabled: boolean
}) {
    const [query, setQuery] = useState('')
    const chosen = new Set(selected)
    const needle = query.trim().toLowerCase()

    const setMany = (names: string[], on: boolean) => {
        const next = new Set(selected)
        names.forEach((name) => (on ? next.add(name) : next.delete(name)))
        onChange([...next])
    }

    return (
        <div className="admin-permission-picker">
            <div className="admin-checklist-head">
                <SearchField value={query} onChange={setQuery} placeholder="Search permissions" />
                <span className="admin-muted">{selected.length} granted</span>
            </div>

            {modules.map((module) => {
                const permissions = module.permissions.filter(
                    (permission) =>
                        !needle ||
                        `${permission.name} ${permission.description ?? ''} ${module.name}`.toLowerCase().includes(needle),
                )

                if (permissions.length === 0) return null

                const names = permissions.map((permission) => permission.name)
                const count = names.filter((name) => chosen.has(name)).length

                return (
                    <fieldset key={module.name} className="admin-module">
                        <legend>
                            <label>
                                <input
                                    type="checkbox"
                                    checked={count === names.length}
                                    ref={(element) => {
                                        if (element) element.indeterminate = count > 0 && count < names.length
                                    }}
                                    disabled={disabled}
                                    onChange={(event) => setMany(names, event.target.checked)}
                                />
                                <strong>{module.name}</strong>
                                <span className="admin-muted">
                                    {count}/{names.length}
                                </span>
                            </label>
                            {module.description && <small>{module.description}</small>}
                        </legend>

                        <div className="admin-module-grid">
                            {permissions.map((permission) => (
                                <label key={permission.name} className="admin-permission-option">
                                    <input
                                        type="checkbox"
                                        checked={chosen.has(permission.name)}
                                        disabled={disabled}
                                        onChange={(event) => setMany([permission.name], event.target.checked)}
                                    />
                                    <span>
                                        <strong>
                                            {permission.name}
                                            <span className={`admin-type is-${permission.type}`}>{permission.type}</span>
                                        </strong>
                                        {permission.description && <small>{permission.description}</small>}
                                    </span>
                                </label>
                            ))}
                        </div>
                    </fieldset>
                )
            })}
        </div>
    )
}
