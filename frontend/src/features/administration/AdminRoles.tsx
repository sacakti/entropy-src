import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { BadgeCheck, Check, Copy, FolderKanban, Globe, LoaderCircle, Lock, Pencil, Plus, Search, Trash2 } from 'lucide-react'

import { adminApi, type AdminModule, type AdminRole, type RoleScope } from '../../api/admin.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import { AdminPanel, ChipList, EmptyRow, SearchField, Tabs } from './AdminPanel'
import { errorMessage, sameSet } from './format'
import ScopeIntro from './ScopeIntro'
import { usePermissions } from './usePermissions'

/** A role to start a new one from, e.g. when duplicating a built-in role. */
interface RoleTemplate {
    title: string
    name: string
    description: string
    scope: RoleScope
    permissions: string[]
}

type Editing = { kind: 'new'; template?: RoleTemplate } | { kind: 'edit'; role: AdminRole }

const SCOPES: { id: RoleScope; label: string; heading: string; text: string; icon: typeof Globe }[] = [
    {
        id: 'global',
        label: 'Global',
        heading: 'Global roles',
        text: 'Applies everywhere; given directly to users and groups.',
        icon: Globe,
    },
    {
        id: 'project',
        label: 'Project',
        heading: 'Project roles',
        text: "Given to people inside a project; covers only that project's workflows, schedules and runs.",
        icon: FolderKanban,
    },
]

/** "Release manager" → "release-manager". */
function slugify(value: string): string {
    return value
        .toLowerCase()
        .normalize('NFKD')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 100)
}

function roleLabel(role: AdminRole): string {
    return role.title || role.name
}

/** Permissions a role of this scope may hold. */
function allowedNames(modules: AdminModule[], scope: RoleScope): Set<string> {
    return new Set(
        modules.flatMap((module) =>
            module.permissions
                .filter((permission) => scope === 'global' || permission.project)
                .map((permission) => permission.name),
        ),
    )
}

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
    const [editing, setEditing] = useState<Editing | null>(() =>
        consumeCreateIntent('role') ? { kind: 'new' } : null,
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

    const totals = useMemo(
        () => ({
            global: allowedNames(modules, 'global').size,
            project: allowedNames(modules, 'project').size,
        }),
        [modules],
    )

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase()
        const sorted = [...roles].sort(
            (a, b) => Number(b.is_builtin) - Number(a.is_builtin) || roleLabel(a).localeCompare(roleLabel(b)),
        )

        return needle
            ? sorted.filter((role) =>
                  [role.name, role.title, role.description, ...role.permissions]
                      .join(' ')
                      .toLowerCase()
                      .includes(needle),
              )
            : sorted
    }, [roles, search])

    const remove = async (role: AdminRole) => {
        const holders =
            role.scope === 'project'
                ? role.project_members
                    ? `${role.project_members} project membership${role.project_members === 1 ? '' : 's'} using it ${role.project_members === 1 ? 'is' : 'are'} removed.`
                    : ''
                : role.users.length + role.groups.length
                  ? `${role.users.length} user(s) and ${role.groups.length} group(s) lose its ${role.permissions.length} permissions.`
                  : ''
        const confirmed = await modal.confirm({
            title: `Delete role ${roleLabel(role)}?`,
            message: `${holders ? `${holders} ` : ''}This cannot be undone.`,
            confirmText: 'Delete role',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setDeleting(role.name)

        try {
            await adminApi.deleteRole(role.name)
            setRoles((current) => current.filter((item) => item.id !== role.id))
            notify.success(`Role '${roleLabel(role)}' deleted.`)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the role.'))
        } finally {
            setDeleting(null)
        }
    }

    const duplicate = (role: AdminRole) => {
        if (!can('roles.create')) return

        const taken = new Set(roles.map((item) => item.name))
        let name = `${role.name}-copy`
        for (let index = 2; taken.has(name); index += 1) name = `${role.name}-copy-${index}`

        setEditing({
            kind: 'new',
            template: {
                title: `${roleLabel(role)} (copy)`,
                name,
                description: role.description ?? '',
                scope: role.scope,
                permissions: role.permissions,
            },
        })
    }

    const openCreate = () => {
        if (can('roles.create')) setEditing({ kind: 'new' })
    }

    useCreateIntent('role', () => setEditing({ kind: 'new' }))

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
                subtitle="A role is a named set of permissions. Built-in roles cover the usual jobs; duplicate one to adjust it."
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
                <ScopeIntro />

                {SCOPES.map((scope) => {
                    const scoped = filtered.filter((role) => role.scope === scope.id)
                    const Icon = scope.icon

                    return (
                        <section key={scope.id} className="admin-role-section" aria-label={scope.heading}>
                            <h3>
                                <Icon size={15} aria-hidden="true" />
                                {scope.heading}
                                <span className="list-count">{scoped.length}</span>
                                <small>{scope.text}</small>
                            </h3>

                            <div className="list-table-wrap">
                                <table className="list-table">
                                    <thead>
                                        <tr>
                                            <th>Role</th>
                                            <th>Permissions</th>
                                            {scope.id === 'global' ? (
                                                <>
                                                    <th>Users</th>
                                                    <th>Groups</th>
                                                </>
                                            ) : (
                                                <th>Used in projects</th>
                                            )}
                                            <th className="list-operations-cell">
                                                <span className="list-operations-heading">Operations</span>
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {loading && roles.length === 0 ? (
                                            <EmptyRow colSpan={5} title="Loading roles…" text="Fetching roles." />
                                        ) : scoped.length === 0 ? (
                                            <EmptyRow
                                                colSpan={5}
                                                title={search ? 'No roles match' : `No ${scope.heading.toLowerCase()} yet`}
                                                text={search ? 'Try a different search.' : 'Create one with the + button.'}
                                            />
                                        ) : (
                                            scoped.map((role) => (
                                                <RoleRow
                                                    key={role.id}
                                                    role={role}
                                                    total={totals[role.scope]}
                                                    canCreate={can('roles.create')}
                                                    canDelete={can('roles.delete')}
                                                    deleting={deleting === role.name}
                                                    onOpen={() => setEditing({ kind: 'edit', role })}
                                                    onDuplicate={() => duplicate(role)}
                                                    onDelete={() => void remove(role)}
                                                />
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    )
                })}
            </AdminPanel>

            {editing && (
                <RoleDialog
                    key={editing.kind === 'edit' ? editing.role.name : `new:${editing.template?.name ?? ''}`}
                    role={editing.kind === 'edit' ? editing.role : null}
                    template={editing.kind === 'new' ? editing.template : undefined}
                    modules={modules}
                    can={can}
                    onClose={() => setEditing(null)}
                    onDuplicate={duplicate}
                    onSaved={() => {
                        setEditing(null)
                        void load()
                    }}
                />
            )}
        </div>
    )
}

function RoleRow({
    role,
    total,
    canCreate,
    canDelete,
    deleting,
    onOpen,
    onDuplicate,
    onDelete,
}: {
    role: AdminRole
    total: number
    canCreate: boolean
    canDelete: boolean
    deleting: boolean
    onOpen: () => void
    onDuplicate: () => void
    onDelete: () => void
}) {
    const label = roleLabel(role)

    return (
        <tr>
            <td>
                <div className="list-name">
                    <span className="list-name-icon" aria-hidden="true">
                        {role.is_builtin ? <Lock size={15} /> : <BadgeCheck size={16} />}
                    </span>
                    <div className="list-name-content">
                        <strong>
                            {label}
                            {role.is_builtin && <span className="admin-badge">Built-in</span>}
                        </strong>
                        <span>
                            <code className="admin-role-name">{role.name}</code>
                            {role.description ? ` · ${role.description}` : ''}
                        </span>
                    </div>
                </div>
            </td>
            <td>
                <div className="admin-meter" title={`${role.permissions.length} of ${total}`}>
                    <span>
                        <span style={{ width: `${total ? Math.min(1, role.permissions.length / total) * 100 : 0}%` }} />
                    </span>
                    <small>
                        {role.permissions.length}/{total}
                    </small>
                </div>
            </td>
            {role.scope === 'global' ? (
                <>
                    <td>
                        <ChipList values={role.users} empty="None" />
                    </td>
                    <td>
                        <ChipList values={role.groups} empty="None" />
                    </td>
                </>
            ) : (
                <td className="list-cell-text">
                    {role.project_members ? (
                        `${role.project_members} membership${role.project_members === 1 ? '' : 's'}`
                    ) : (
                        <span className="admin-muted">None</span>
                    )}
                </td>
            )}
            <td>
                <div className="list-operations">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                        aria-label={`${role.is_builtin ? 'View' : 'Edit'} ${label}`}
                        title={role.is_builtin ? 'View permissions' : 'Edit'}
                        onClick={onOpen}
                    >
                        {role.is_builtin ? <Search size={15} /> : <Pencil size={15} />}
                    </button>
                    {canCreate && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label={`Duplicate ${label} as a custom role`}
                            title="Duplicate as custom role"
                            onClick={onDuplicate}
                        >
                            <Copy size={15} />
                        </button>
                    )}
                    {canDelete && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                            aria-label={`Delete ${label}`}
                            title={role.is_builtin ? 'Built-in roles cannot be deleted' : 'Delete'}
                            disabled={role.is_builtin || deleting}
                            onClick={onDelete}
                        >
                            {deleting ? <LoaderCircle size={15} className="entropy-spin" /> : <Trash2 size={15} />}
                        </button>
                    )}
                </div>
            </td>
        </tr>
    )
}

type RoleTab = 'details' | 'permissions' | 'assigned'

function RoleDialog({
    role,
    template,
    modules,
    can,
    onClose,
    onDuplicate,
    onSaved,
}: {
    role: AdminRole | null
    template?: RoleTemplate
    modules: AdminModule[]
    can: (permission: string) => boolean
    onClose: () => void
    onDuplicate: (role: AdminRole) => void
    onSaved: () => void
}) {
    const { notify } = useFeedback()
    const creating = role === null
    const locked = role?.is_builtin ?? false

    const [tab, setTab] = useState<RoleTab>(locked ? 'permissions' : 'details')
    const [title, setTitle] = useState(role?.title ?? template?.title ?? '')
    const [name, setName] = useState(role?.name ?? template?.name ?? '')
    // While creating, the name follows the title until edited by hand.
    const [nameTouched, setNameTouched] = useState(!creating || Boolean(template))
    const [scope, setScope] = useState<RoleScope>(role?.scope ?? template?.scope ?? 'global')
    const [description, setDescription] = useState(role?.description ?? template?.description ?? '')
    const [granted, setGranted] = useState<string[]>(role?.permissions ?? template?.permissions ?? [])
    const [saving, setSaving] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    const canDetails = !locked && (creating ? can('roles.create') : can('roles.modify'))
    const canPermissions = !locked && can('roles.permissions')

    const allowed = useMemo(() => allowedNames(modules, scope), [modules, scope])
    // A project role may only hold project permissions; drop the rest silently.
    const effective = granted.filter((permission) => allowed.has(permission) || modules.length === 0)
    const dropped = granted.length - effective.length

    const detailsDirty =
        creating ||
        name.trim() !== role.name ||
        title.trim() !== (role.title ?? '') ||
        description.trim() !== (role.description ?? '')
    const permissionsDirty = !sameSet(effective, role?.permissions ?? [])

    const changeTitle = (value: string) => {
        setTitle(value)
        if (!nameTouched) setName(slugify(value))
    }

    const save = async (event?: FormEvent) => {
        event?.preventDefault()

        if (saving || locked) return

        setSaving(true)
        setFormError(null)

        try {
            if (!title.trim()) throw new Error('Enter a title.')
            if (!name.trim()) throw new Error('Enter a name.')

            let current = name.trim()

            if (creating) {
                await adminApi.createRole({
                    name: current,
                    title: title.trim(),
                    description: description.trim() || null,
                    scope,
                })
            } else if (detailsDirty) {
                current = (
                    await adminApi.updateRole(role.name, {
                        name: current,
                        title: title.trim(),
                        description: description.trim(),
                    })
                ).name
            }

            if (permissionsDirty && (creating ? effective.length > 0 : true)) {
                if (canPermissions) {
                    try {
                        await adminApi.setRolePermissions(current, effective)
                    } catch (cause) {
                        if (!creating) throw cause
                        notify.error(
                            `Role '${title.trim()}' was created, but its permissions were not saved: ${errorMessage(cause, 'unknown error')}`,
                        )
                        onSaved()
                        return
                    }
                } else if (creating) {
                    notify.warning(`Role '${title.trim()}' was created without permissions; you may not grant them.`)
                }
            }

            notify.success(`Role '${title.trim()}' ${creating ? 'created' : 'updated'}.`)
            onSaved()
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to save the role.'))
        } finally {
            setSaving(false)
        }
    }

    const scopeInfo = SCOPES.find((item) => item.id === scope) ?? SCOPES[0]

    return (
        <Dialog
            title={
                creating
                    ? template
                        ? 'Duplicate as custom role'
                        : 'Create role'
                    : locked
                      ? `${roleLabel(role)} (built-in)`
                      : `Edit ${roleLabel(role)}`
            }
            subtitle={
                locked
                    ? 'Built-in roles cannot be changed. Duplicate one to make an adjustable copy.'
                    : `${scopeInfo.label} role · ${scopeInfo.text}`
            }
            icon={locked ? <Lock size={18} /> : <BadgeCheck size={18} />}
            onClose={onClose}
            className="admin-dialog admin-dialog-wide"
            footer={
                locked ? (
                    <>
                        {role && can('roles.create') && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary"
                                onClick={() => onDuplicate(role)}
                            >
                                <Copy size={15} />
                                Duplicate as custom role
                            </button>
                        )}
                        <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
                            Close
                        </button>
                    </>
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
                    { id: 'permissions' as const, label: 'Permissions', count: effective.length },
                    ...(creating
                        ? []
                        : [
                              {
                                  id: 'assigned' as const,
                                  label: 'Assigned to',
                                  count:
                                      role.scope === 'project'
                                          ? role.project_members
                                          : role.users.length + role.groups.length,
                              },
                          ]),
                ]}
                active={tab}
                onChange={setTab}
            />

            <form id="admin-role-form" className="admin-form" onSubmit={save}>
                {tab === 'details' && (
                    <div className="admin-form-grid">
                        <label className="admin-field">
                            <span>Title</span>
                            <input
                                value={title}
                                onChange={(event) => changeTitle(event.target.value)}
                                placeholder="e.g. Release manager"
                                disabled={!canDetails}
                                maxLength={100}
                                required
                            />
                        </label>
                        <label className="admin-field">
                            <span>Name</span>
                            <input
                                value={name}
                                onChange={(event) => {
                                    setNameTouched(true)
                                    setName(event.target.value)
                                }}
                                placeholder="e.g. release-manager"
                                disabled={!canDetails}
                                maxLength={100}
                                spellCheck={false}
                                required
                            />
                            <small>Short identifier used by the API and the ent CLI.</small>
                        </label>

                        <fieldset className="admin-field admin-field-wide admin-scope-field" disabled={!creating || !canDetails}>
                            <span>Scope</span>
                            <div className="admin-scope-options">
                                {SCOPES.map((option) => {
                                    const Icon = option.icon

                                    return (
                                        <label
                                            key={option.id}
                                            className={`admin-scope-option${scope === option.id ? ' is-active' : ''}`}
                                        >
                                            <input
                                                type="radio"
                                                name="role-scope"
                                                value={option.id}
                                                checked={scope === option.id}
                                                onChange={() => setScope(option.id)}
                                            />
                                            <Icon size={16} aria-hidden="true" />
                                            <span>
                                                <strong>{option.label}</strong>
                                                <small>{option.text}</small>
                                            </span>
                                        </label>
                                    )
                                })}
                            </div>
                            {!creating && <small>The scope of an existing role cannot be changed.</small>}
                            {creating && dropped > 0 && (
                                <small>
                                    {dropped} permission{dropped === 1 ? '' : 's'} that only global roles may hold will not be
                                    granted.
                                </small>
                            )}
                        </fieldset>

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
                    <>
                        {scope === 'project' && !locked && (
                            <p className="admin-muted">
                                Only permissions that make sense inside one project are listed for project roles.
                            </p>
                        )}
                        {!canPermissions && !locked && (
                            <p className="admin-muted">You may view these permissions but not change them (needs roles.permissions).</p>
                        )}
                        <PermissionPicker
                            modules={modules}
                            allowed={allowed}
                            selected={effective}
                            onChange={setGranted}
                            disabled={!canPermissions}
                            onlySelected={locked}
                        />
                    </>
                )}

                {tab === 'assigned' && role && (
                    <div className="admin-assigned">
                        {role.scope === 'project' ? (
                            <p>
                                {role.project_members
                                    ? `Used by ${role.project_members} project membership${role.project_members === 1 ? '' : 's'}.`
                                    : 'No project member holds this role yet.'}{' '}
                                <span className="admin-muted">
                                    Give project roles under Administration › Projects, or on a user’s or group’s Projects tab.
                                </span>
                            </p>
                        ) : (
                            <>
                                <section>
                                    <h3>Users ({role.users.length})</h3>
                                    <ChipList values={role.users} max={50} empty="No users hold this role directly." />
                                </section>
                                <section>
                                    <h3>Groups ({role.groups.length})</h3>
                                    <ChipList values={role.groups} max={50} empty="No groups grant this role." />
                                </section>
                                <p className="admin-muted">Assign global roles from Administration › Users or › Groups.</p>
                            </>
                        )}
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
    allowed,
    selected,
    onChange,
    disabled,
    onlySelected,
}: {
    modules: AdminModule[]
    /** Permissions this role's scope may hold; others are not shown. */
    allowed: Set<string>
    selected: string[]
    onChange: (selected: string[]) => void
    disabled: boolean
    /** Show only granted permissions (read-only view of a built-in role). */
    onlySelected?: boolean
}) {
    const [query, setQuery] = useState('')
    const chosen = new Set(selected)
    const needle = query.trim().toLowerCase()

    const setMany = (names: string[], on: boolean) => {
        const next = new Set(selected)
        names.forEach((name) => (on ? next.add(name) : next.delete(name)))
        onChange([...next])
    }

    const visibleModules = modules
        .map((module) => ({
            module,
            permissions: module.permissions.filter(
                (permission) =>
                    allowed.has(permission.name) &&
                    (!onlySelected || chosen.has(permission.name)) &&
                    (!needle ||
                        `${permission.name} ${permission.description ?? ''} ${module.name}`.toLowerCase().includes(needle)),
            ),
        }))
        .filter(({ permissions }) => permissions.length > 0)

    return (
        <div className="admin-permission-picker">
            <div className="admin-checklist-head">
                <SearchField value={query} onChange={setQuery} placeholder="Search permissions" />
                <span className="admin-muted">
                    {selected.length}/{allowed.size} granted
                </span>
            </div>

            {visibleModules.length === 0 && (
                <p className="admin-checklist-empty">
                    {needle ? `Nothing matches “${query}”.` : onlySelected ? 'This role holds no permissions.' : 'No permissions.'}
                </p>
            )}

            {visibleModules.map(({ module, permissions }) => {
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
