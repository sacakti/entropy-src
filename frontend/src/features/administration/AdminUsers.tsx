import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
    Check,
    Copy,
    Eye,
    EyeOff,
    KeyRound,
    LoaderCircle,
    Lock,
    Pencil,
    Plus,
    Power,
    Trash2,
    UserRound,
    Wand2,
} from 'lucide-react'

import { adminApi, type AdminGroup, type AdminRole, type AdminUser } from '../../api/admin.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import { AdminPanel, Checklist, ChipList, EmptyRow, SearchField, Tabs } from './AdminPanel'
import { errorMessage, formatDate, sameSet } from './format'
import { usePermissions } from './usePermissions'

type StatusFilter = 'all' | 'active' | 'disabled'

/** A strong random password that satisfies Entropy's password rules. */
function generatePassword(): string {
    const sets = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnpqrstuvwxyz', '23456789', '!#$%&*+-=?@^_']
    const all = sets.join('')
    const random = new Uint32Array(20)
    crypto.getRandomValues(random)

    const characters = Array.from(random, (value, index) => {
        const pool = index < sets.length ? sets[index] : all
        return pool[value % pool.length]
    })

    // Shuffle so the guaranteed characters are not always first.
    for (let index = characters.length - 1; index > 0; index -= 1) {
        const swap = random[index] % (index + 1)
        ;[characters[index], characters[swap]] = [characters[swap], characters[index]]
    }

    return characters.join('')
}

function initials(user: AdminUser): string {
    const words = (user.full_name ?? '').trim().split(/\s+/).filter(Boolean)
    if (words.length >= 2) return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase()
    return (words[0]?.[0] ?? user.username[0] ?? '?').toUpperCase()
}

export default function AdminUsers() {
    const { notify, modal } = useFeedback()
    const permissions = usePermissions()
    const can = (permission: string) => permissions?.has(permission) ?? false

    const [users, setUsers] = useState<AdminUser[]>([])
    const [roles, setRoles] = useState<AdminRole[]>([])
    const [groups, setGroups] = useState<AdminGroup[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [search, setSearch] = useState('')
    const [status, setStatus] = useState<StatusFilter>('all')
    const [editing, setEditing] = useState<AdminUser | 'new' | null>(() =>
        consumeCreateIntent('user') ? 'new' : null,
    )
    const [busyUser, setBusyUser] = useState<string | null>(null)
    const searchRef = useRef<HTMLInputElement>(null)

    const load = useCallback(async () => {
        try {
            const [userList, roleList, groupList] = await Promise.all([
                adminApi.users(),
                // Pickers only; a user without these permissions still sees users.
                adminApi.roles().catch(() => ({ items: [] as AdminRole[] })),
                adminApi.groups().catch(() => ({ items: [] as AdminGroup[] })),
            ])
            setUsers(userList.items)
            setRoles(roleList.items)
            setGroups(groupList.items)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load users.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        // Load after mount; `load` only sets state once its requests settle.
        Promise.resolve().then(load)
    }, [load])

    const refresh = () => {
        setRefreshing(true)
        void load()
    }

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase()

        return users.filter(
            (user) =>
                (status === 'all' || (status === 'active') === user.is_active) &&
                (!needle ||
                    [user.username, user.full_name, user.email, ...user.roles, ...user.groups]
                        .join(' ')
                        .toLowerCase()
                        .includes(needle)),
        )
    }, [search, status, users])

    const replace = (updated: AdminUser) =>
        setUsers((current) => current.map((user) => (user.id === updated.id ? updated : user)))

    const toggleActive = async (user: AdminUser) => {
        const disabling = user.is_active

        if (
            disabling &&
            !(await modal.confirm({
                title: `Disable ${user.username}?`,
                message: 'They are signed out everywhere and cannot sign in until enabled again.',
                confirmText: 'Disable user',
                cancelText: 'Cancel',
                destructive: true,
            }))
        ) {
            return
        }

        setBusyUser(user.username)

        try {
            replace(await adminApi.setUserActive(user.username, !disabling))
            notify.success(`${user.username} ${disabling ? 'disabled' : 'enabled'}.`)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to change the account status.'))
        } finally {
            setBusyUser(null)
        }
    }

    const remove = async (user: AdminUser) => {
        const confirmed = await modal.confirm({
            title: `Delete ${user.username}?`,
            message:
                'The account, its role assignments and group memberships are removed. This cannot be undone.',
            confirmText: 'Delete user',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setBusyUser(user.username)

        try {
            await adminApi.deleteUser(user.username)
            setUsers((current) => current.filter((item) => item.id !== user.id))
            notify.success(`User '${user.username}' deleted.`)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the user.'))
        } finally {
            setBusyUser(null)
        }
    }

    const openCreate = () => {
        if (can('users.create')) setEditing('new')
    }

    useCreateIntent('user', () => setEditing('new'))

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

    const activeCount = users.filter((user) => user.is_active).length

    return (
        <div className="list-page admin-page">
            <AdminPanel
                title="Users"
                count={users.length}
                subtitle={`${activeCount} active · ${users.length - activeCount} disabled`}
                error={error}
                refreshing={refreshing || loading}
                onRefresh={refresh}
                actions={
                    can('users.create') && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon"
                            aria-label="Create user"
                            title="Create user (Ctrl+N)"
                            onClick={openCreate}
                        >
                            <Plus size={20} />
                        </button>
                    )
                }
                toolbar={
                    <>
                        <SearchField
                            inputRef={searchRef}
                            value={search}
                            onChange={setSearch}
                            placeholder="Search users, roles or groups…"
                        />
                        <label className="list-filter">
                            <span>Status</span>
                            <select
                                className="entropy-select"
                                value={status}
                                onChange={(event) => setStatus(event.target.value as StatusFilter)}
                            >
                                <option value="all">All users</option>
                                <option value="active">Active</option>
                                <option value="disabled">Disabled</option>
                            </select>
                        </label>
                    </>
                }
            >
                <div className="list-table-wrap">
                    <table className="list-table">
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Email</th>
                                <th>Status</th>
                                <th>Roles</th>
                                <th>Groups</th>
                                <th>Created</th>
                                <th className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && users.length === 0 ? (
                                <EmptyRow colSpan={7} title="Loading users…" text="Fetching accounts." />
                            ) : filtered.length === 0 ? (
                                <EmptyRow
                                    colSpan={7}
                                    title="No users found"
                                    text={search || status !== 'all' ? 'Try a different search or filter.' : 'Create the first user.'}
                                />
                            ) : (
                                filtered.map((user) => (
                                    <tr key={user.id} className={user.is_active ? undefined : 'is-muted'}>
                                        <td>
                                            <div className="list-name">
                                                <span className="admin-avatar" aria-hidden="true">
                                                    {initials(user)}
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>{user.full_name || user.username}</strong>
                                                    <span>
                                                        @{user.username}
                                                        {user.is_system && (
                                                            <span className="admin-badge" title="Built-in administrator">
                                                                <Lock size={10} /> System
                                                            </span>
                                                        )}
                                                    </span>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="list-cell-text">{user.email || <span className="admin-muted">—</span>}</td>
                                        <td>
                                            <span className={`list-status ${user.is_active ? 'list-status-enabled' : 'list-status-disabled'}`}>
                                                <span className="list-status-dot" />
                                                {user.is_active ? 'Active' : 'Disabled'}
                                            </span>
                                        </td>
                                        <td>
                                            <ChipList values={user.roles} tone="accent" />
                                        </td>
                                        <td>
                                            <ChipList values={user.groups} />
                                        </td>
                                        <td className="list-cell-text">{formatDate(user.created_at)}</td>
                                        <td>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Edit ${user.username}`}
                                                    title="Edit"
                                                    onClick={() => setEditing(user)}
                                                >
                                                    <Pencil size={15} />
                                                </button>
                                                {can(user.is_active ? 'users.disable' : 'users.enable') && (
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`${user.is_active ? 'Disable' : 'Enable'} ${user.username}`}
                                                        title={user.is_active ? 'Disable' : 'Enable'}
                                                        disabled={user.is_system || busyUser === user.username}
                                                        onClick={() => void toggleActive(user)}
                                                    >
                                                        <Power size={15} />
                                                    </button>
                                                )}
                                                {can('users.delete') && (
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                        aria-label={`Delete ${user.username}`}
                                                        title="Delete"
                                                        disabled={user.is_system || busyUser === user.username}
                                                        onClick={() => void remove(user)}
                                                    >
                                                        {busyUser === user.username ? (
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
                <UserDialog
                    user={editing === 'new' ? null : editing}
                    roles={roles}
                    groups={groups}
                    can={can}
                    onClose={() => setEditing(null)}
                    onSaved={(saved, created) => {
                        if (created) setUsers((current) => [...current, saved].sort((a, b) => a.username.localeCompare(b.username)))
                        else replace(saved)
                        setEditing(null)
                    }}
                />
            )}
        </div>
    )
}

type UserTab = 'profile' | 'roles' | 'groups' | 'password'

function UserDialog({
    user,
    roles,
    groups,
    can,
    onClose,
    onSaved,
}: {
    user: AdminUser | null
    roles: AdminRole[]
    groups: AdminGroup[]
    can: (permission: string) => boolean
    onClose: () => void
    onSaved: (user: AdminUser, created: boolean) => void
}) {
    const { notify } = useFeedback()
    const creating = user === null

    const [tab, setTab] = useState<UserTab>('profile')
    const [username, setUsername] = useState('')
    const [fullName, setFullName] = useState(user?.full_name ?? '')
    const [email, setEmail] = useState(user?.email ?? '')
    const [password, setPassword] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [userRoles, setUserRoles] = useState<string[]>(user?.roles ?? [])
    const [userGroups, setUserGroups] = useState<string[]>(user?.groups ?? [])
    const [saving, setSaving] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)
    const [temporary, setTemporary] = useState<string | null>(null)
    const [copied, setCopied] = useState(false)

    const canProfile = creating ? can('users.create') : can('users.modify')
    const canRoles = can('users.roles')
    const canGroups = can('groups.users')

    const profileDirty =
        !creating && (fullName.trim() !== (user.full_name ?? '') || email.trim() !== (user.email ?? ''))
    const rolesDirty = !creating && !sameSet(userRoles, user.roles)
    const groupsDirty = !creating && !sameSet(userGroups, user.groups)
    const dirty = creating || profileDirty || rolesDirty || groupsDirty

    const save = async (event?: FormEvent) => {
        event?.preventDefault()

        if (saving) return

        setSaving(true)
        setFormError(null)

        try {
            if (creating) {
                if (!username.trim()) throw new Error('Enter a username.')
                if (!password) throw new Error('Enter or generate a password.')

                const created = await adminApi.createUser({
                    username: username.trim(),
                    password,
                    full_name: fullName.trim() || null,
                    email: email.trim() || null,
                    roles: canRoles ? userRoles : [],
                    groups: canGroups ? userGroups : [],
                })
                notify.success(`User '${created.username}' created.`)
                onSaved(created, true)
                return
            }

            let saved = user

            if (profileDirty) {
                saved = await adminApi.updateUser(user.username, {
                    full_name: fullName.trim() || null,
                    email: email.trim() || null,
                })
            }
            if (rolesDirty) saved = await adminApi.setUserRoles(user.username, userRoles)
            if (groupsDirty) saved = await adminApi.setUserGroups(user.username, userGroups)

            notify.success(`User '${user.username}' updated.`)
            onSaved(saved, false)
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to save the user.'))
        } finally {
            setSaving(false)
        }
    }

    const changePassword = async (generate: boolean) => {
        if (!user || saving) return

        setSaving(true)
        setFormError(null)
        setTemporary(null)

        try {
            const result = await adminApi.setUserPassword(user.username, generate ? null : password)
            setPassword('')
            setTemporary(result.password)
            notify.success(result.message)
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to change the password.'))
        } finally {
            setSaving(false)
        }
    }

    const tabs: { id: UserTab; label: string; count?: number }[] = [
        { id: 'profile', label: creating ? 'Account' : 'Profile' },
        ...(canRoles ? [{ id: 'roles' as const, label: 'Roles', count: userRoles.length }] : []),
        ...(canGroups ? [{ id: 'groups' as const, label: 'Groups', count: userGroups.length }] : []),
        ...(!creating && can('users.modify') ? [{ id: 'password' as const, label: 'Password' }] : []),
    ]

    return (
        <Dialog
            title={creating ? 'Create user' : `Edit ${user.username}`}
            subtitle={
                creating
                    ? 'New accounts can sign in to the web UI and the ent CLI.'
                    : `${user.is_active ? 'Active' : 'Disabled'} · created ${formatDate(user.created_at)}`
            }
            icon={<UserRound size={18} />}
            onClose={onClose}
            className="admin-dialog"
            footer={
                tab !== 'password' && (
                    <>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Cancel
                        </button>
                        <button
                            type="submit"
                            form="admin-user-form"
                            className="entropy-button entropy-button-primary"
                            disabled={saving || !dirty}
                        >
                            {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Check size={15} />}
                            {creating ? 'Create user' : 'Save changes'}
                        </button>
                    </>
                )
            }
        >
            <Tabs tabs={tabs} active={tab} onChange={setTab} />

            <form id="admin-user-form" className="admin-form" onSubmit={save}>
                {tab === 'profile' && (
                    <div className="admin-form-grid">
                        <label className="admin-field">
                            <span>Username</span>
                            {creating ? (
                                <input
                                    value={username}
                                    onChange={(event) => setUsername(event.target.value)}
                                    placeholder="e.g. jsmith"
                                    autoComplete="off"
                                    spellCheck={false}
                                    maxLength={64}
                                    required
                                />
                            ) : (
                                <input value={user.username} disabled readOnly />
                            )}
                        </label>
                        <label className="admin-field">
                            <span>Full name</span>
                            <input
                                value={fullName}
                                onChange={(event) => setFullName(event.target.value)}
                                placeholder="Jane Smith"
                                disabled={!canProfile}
                                maxLength={120}
                            />
                        </label>
                        <label className="admin-field admin-field-wide">
                            <span>Email</span>
                            <input
                                type="email"
                                value={email}
                                onChange={(event) => setEmail(event.target.value)}
                                placeholder="jane@example.com"
                                disabled={!canProfile}
                                maxLength={254}
                            />
                        </label>
                        {creating && (
                            <PasswordField
                                value={password}
                                onChange={setPassword}
                                visible={showPassword}
                                onToggleVisible={() => setShowPassword((value) => !value)}
                                onGenerate={() => {
                                    setPassword(generatePassword())
                                    setShowPassword(true)
                                }}
                                hint="Share it securely; the user can change it under Settings."
                            />
                        )}
                    </div>
                )}

                {tab === 'roles' && (
                    <Checklist
                        items={roles.map((role) => ({
                            value: role.name,
                            detail: role.description ?? `${role.permissions.length} permissions`,
                        }))}
                        selected={userRoles}
                        onChange={setUserRoles}
                        placeholder="Search roles"
                        emptyText="No roles exist yet."
                    />
                )}

                {tab === 'groups' && (
                    <Checklist
                        items={groups.map((group) => ({
                            value: group.name,
                            detail:
                                group.description ??
                                (group.roles.length ? `Roles: ${group.roles.join(', ')}` : 'No roles'),
                        }))}
                        selected={userGroups}
                        onChange={setUserGroups}
                        placeholder="Search groups"
                        emptyText="No groups exist yet. Create one under Administration › Groups."
                    />
                )}
            </form>

            {tab === 'password' && user && (
                <div className="admin-password">
                    <PasswordField
                        value={password}
                        onChange={setPassword}
                        visible={showPassword}
                        onToggleVisible={() => setShowPassword((value) => !value)}
                        label="New password"
                        hint="At least 8 characters; common passwords are refused."
                    />
                    <div className="admin-password-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            onClick={() => void changePassword(true)}
                            disabled={saving}
                        >
                            <Wand2 size={15} />
                            Generate temporary password
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            onClick={() => void changePassword(false)}
                            disabled={saving || !password}
                        >
                            {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <KeyRound size={15} />}
                            Set password
                        </button>
                    </div>

                    {temporary && (
                        <div className="admin-temporary" role="status">
                            <span>Temporary password for {user.username} — shown once:</span>
                            <code>{temporary}</code>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="Copy password"
                                onClick={() => {
                                    void navigator.clipboard.writeText(temporary).then(() => setCopied(true))
                                }}
                            >
                                {copied ? <Check size={14} /> : <Copy size={14} />}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {formError && (
                <div className="entropy-alert entropy-alert-error admin-form-error" role="alert">
                    <span>{formError}</span>
                </div>
            )}
        </Dialog>
    )
}

function PasswordField({
    value,
    onChange,
    visible,
    onToggleVisible,
    onGenerate,
    label = 'Password',
    hint,
}: {
    value: string
    onChange: (value: string) => void
    visible: boolean
    onToggleVisible: () => void
    onGenerate?: () => void
    label?: string
    hint?: string
}) {
    return (
        <label className="admin-field admin-field-wide">
            <span>{label}</span>
            <div className="admin-password-input">
                <input
                    type={visible ? 'text' : 'password'}
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                    autoComplete="new-password"
                    spellCheck={false}
                />
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label={visible ? 'Hide password' : 'Show password'}
                    onClick={onToggleVisible}
                >
                    {visible ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
                {onGenerate && (
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        onClick={onGenerate}
                    >
                        <Wand2 size={14} />
                        Generate
                    </button>
                )}
            </div>
            {hint && <small>{hint}</small>}
        </label>
    )
}
