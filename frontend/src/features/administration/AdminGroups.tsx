import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Check, LoaderCircle, Pencil, Plus, Trash2, UsersRound } from 'lucide-react'

import { adminApi, type AdminGroup, type AdminRole, type AdminUser, type MembershipInput } from '../../api/admin.api'
import { projectsApi, type ProjectSummary } from '../../api/projects.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import { AdminPanel, Checklist, ChipList, EmptyRow, SearchField, Tabs } from './AdminPanel'
import { errorMessage, formatDate, sameSet } from './format'
import { membershipLabels, sameMemberships, toMembershipInputs, uniqueMemberships } from './memberships'
import { missingPermission } from './permissionReason'
import { ProjectMembershipEditor } from './ProjectMemberships'
import { usePermissions } from './usePermissions'

export default function AdminGroups() {
    const { notify, modal } = useFeedback()
    const permissions = usePermissions()
    const can = (permission: string) => permissions?.has(permission) ?? false

    const [groups, setGroups] = useState<AdminGroup[]>([])
    const [users, setUsers] = useState<AdminUser[]>([])
    const [roles, setRoles] = useState<AdminRole[]>([])
    const [projects, setProjects] = useState<ProjectSummary[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [search, setSearch] = useState('')
    const [editing, setEditing] = useState<AdminGroup | 'new' | null>(() =>
        consumeCreateIntent('group') ? 'new' : null,
    )
    const [deleting, setDeleting] = useState<string | null>(null)
    const searchRef = useRef<HTMLInputElement>(null)

    const load = useCallback(async () => {
        try {
            const [groupList, userList, roleList, projectList] = await Promise.all([
                adminApi.groups(),
                adminApi.users().catch(() => ({ items: [] as AdminUser[] })),
                adminApi.roles().catch(() => ({ items: [] as AdminRole[] })),
                projectsApi.list().catch(() => ({ items: [] as ProjectSummary[] })),
            ])
            setGroups(groupList.items)
            setUsers(userList.items)
            setRoles(roleList.items)
            setProjects(projectList.items)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load groups.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        // Load after mount; `load` only sets state once its requests settle.
        Promise.resolve().then(load)
    }, [load])

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase()

        return needle
            ? groups.filter((group) =>
                  [
                      group.name,
                      group.description,
                      ...group.users,
                      ...group.roles,
                      ...membershipLabels(group.projects ?? []),
                  ]
                      .join(' ')
                      .toLowerCase()
                      .includes(needle),
              )
            : groups
    }, [groups, search])

    const remove = async (group: AdminGroup) => {
        const confirmed = await modal.confirm({
            title: `Delete group ${group.name}?`,
            message: `${group.users.length} member${group.users.length === 1 ? '' : 's'} lose the roles this group grants. This cannot be undone.`,
            confirmText: 'Delete group',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setDeleting(group.name)

        try {
            await adminApi.deleteGroup(group.name)
            setGroups((current) => current.filter((item) => item.id !== group.id))
            notify.success(`Group '${group.name}' deleted.`)
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the group.'))
        } finally {
            setDeleting(null)
        }
    }

    const openCreate = () => {
        if (can('groups.create')) setEditing('new')
    }

    useCreateIntent('group', () => setEditing('new'))

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
                title="Groups"
                count={groups.length}
                subtitle="Groups give every member the roles assigned to the group."
                error={error}
                refreshing={refreshing || loading}
                onRefresh={() => {
                    setRefreshing(true)
                    void load()
                }}
                actions={
                    can('groups.create') && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon"
                            aria-label="Create group"
                            title="Create group (Ctrl+N)"
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
                        placeholder="Search groups, members, roles or projects…"
                    />
                }
            >
                <div className="list-table-wrap">
                    <table className="list-table">
                        <thead>
                            <tr>
                                <th>Group</th>
                                <th>Members</th>
                                <th>Global roles</th>
                                <th>Projects</th>
                                <th>Updated</th>
                                <th className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && groups.length === 0 ? (
                                <EmptyRow colSpan={6} title="Loading groups…" text="Fetching groups." />
                            ) : filtered.length === 0 ? (
                                <EmptyRow
                                    colSpan={6}
                                    title={search ? 'No groups match' : 'No groups yet'}
                                    text={
                                        search
                                            ? 'Try a different search.'
                                            : 'Create a group to give several users the same roles.'
                                    }
                                />
                            ) : (
                                filtered.map((group) => (
                                    <tr key={group.id}>
                                        <td>
                                            <div className="list-name">
                                                <span className="list-name-icon" aria-hidden="true">
                                                    <UsersRound size={16} />
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>{group.name}</strong>
                                                    <span>{group.description || 'No description'}</span>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <ChipList values={group.users} empty="No members" />
                                        </td>
                                        <td>
                                            <ChipList values={group.roles} tone="accent" empty="No roles" />
                                        </td>
                                        <td>
                                            <ChipList values={membershipLabels(group.projects ?? [])} max={2} empty="None" />
                                        </td>
                                        <td className="list-cell-text">{formatDate(group.updated_at)}</td>
                                        <td>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Edit ${group.name}`}
                                                    title="Edit"
                                                    onClick={() => setEditing(group)}
                                                >
                                                    <Pencil size={15} />
                                                </button>
                                                {can('groups.delete') && (
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                        aria-label={`Delete ${group.name}`}
                                                        title="Delete"
                                                        disabled={deleting === group.name}
                                                        onClick={() => void remove(group)}
                                                    >
                                                        {deleting === group.name ? (
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
                <GroupDialog
                    group={editing === 'new' ? null : editing}
                    users={users}
                    roles={roles}
                    projects={projects}
                    can={can}
                    permissions={permissions}
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

type GroupTab = 'details' | 'members' | 'roles' | 'projects'

function GroupDialog({
    group,
    users,
    roles,
    projects,
    can,
    permissions,
    onClose,
    onSaved,
}: {
    group: AdminGroup | null
    users: AdminUser[]
    roles: AdminRole[]
    projects: ProjectSummary[]
    can: (permission: string) => boolean
    permissions: Set<string> | null
    onClose: () => void
    onSaved: () => void
}) {
    const { notify } = useFeedback()
    const creating = group === null

    const [tab, setTab] = useState<GroupTab>('details')
    const [name, setName] = useState(group?.name ?? '')
    const [description, setDescription] = useState(group?.description ?? '')
    const [members, setMembers] = useState<string[]>(group?.users ?? [])
    const [groupRoles, setGroupRoles] = useState<string[]>(group?.roles ?? [])
    const [memberships, setMemberships] = useState<MembershipInput[]>(() =>
        toMembershipInputs(group?.projects ?? []),
    )
    const [saving, setSaving] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    const canDetails = creating ? can('groups.create') : can('groups.modify')
    const canMembers = can('groups.users')
    const canRoles = can('groups.roles')
    const canProjects = can('projects.manage')
    const globalRoles = roles.filter((role) => role.scope !== 'project')
    const projectRoles = roles.filter((role) => role.scope === 'project')

    const detailsDirty =
        creating || name.trim() !== group.name || description.trim() !== (group.description ?? '')
    const membersDirty = !sameSet(members, group?.users ?? [])
    const rolesDirty = !sameSet(groupRoles, group?.roles ?? [])
    const projectsDirty = canProjects && !sameMemberships(memberships, toMembershipInputs(group?.projects ?? []))

    const save = async (event?: FormEvent) => {
        event?.preventDefault()

        if (saving) return

        setSaving(true)
        setFormError(null)

        try {
            if (!name.trim()) throw new Error('Enter a group name.')

            let current = name.trim()

            if (creating) {
                await adminApi.createGroup({ name: current, description: description.trim() || null })
            } else if (detailsDirty) {
                const saved = await adminApi.updateGroup(group.name, {
                    name: current,
                    description: description.trim(),
                })
                current = saved.name
            }

            if (canMembers && membersDirty) await adminApi.setGroupUsers(current, members)
            if (canRoles && rolesDirty) await adminApi.setGroupRoles(current, groupRoles)
            if (projectsDirty) await adminApi.setGroupProjects(current, uniqueMemberships(memberships))

            notify.success(`Group '${current}' ${creating ? 'created' : 'updated'}.`)
            onSaved()
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to save the group.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={creating ? 'Create group' : `Edit ${group.name}`}
            subtitle="Members receive every global role and project role given to the group."
            icon={<UsersRound size={18} />}
            onClose={onClose}
            className="admin-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="submit"
                        form="admin-group-form"
                        className="entropy-button entropy-button-primary"
                        disabled={saving || !(detailsDirty || membersDirty || rolesDirty || projectsDirty)}
                    >
                        {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Check size={15} />}
                        {creating ? 'Create group' : 'Save changes'}
                    </button>
                </>
            }
        >
            <Tabs
                tabs={[
                    { id: 'details' as const, label: 'Details' },
                    ...(canMembers ? [{ id: 'members' as const, label: 'Members', count: members.length }] : []),
                    ...(canRoles ? [{ id: 'roles' as const, label: 'Global roles', count: groupRoles.length }] : []),
                    ...(canProjects || memberships.length
                        ? [{ id: 'projects' as const, label: 'Projects', count: memberships.length }]
                        : []),
                ]}
                active={tab}
                onChange={setTab}
            />

            <form id="admin-group-form" className="admin-form" onSubmit={save}>
                {tab === 'details' && (
                    <div className="admin-form-grid">
                        <label className="admin-field admin-field-wide">
                            <span>Name</span>
                            <input
                                value={name}
                                onChange={(event) => setName(event.target.value)}
                                placeholder="e.g. operators"
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
                                placeholder="Who belongs to this group?"
                                disabled={!canDetails}
                                maxLength={500}
                                rows={3}
                            />
                        </label>
                    </div>
                )}

                {tab === 'members' && (
                    <Checklist
                        items={users.map((user) => ({
                            value: user.username,
                            label: user.full_name ? `${user.full_name} (@${user.username})` : user.username,
                            detail: user.is_active ? user.email : 'Disabled',
                        }))}
                        selected={members}
                        onChange={setMembers}
                        placeholder="Search users"
                        emptyText="No users found."
                    />
                )}

                {tab === 'roles' && (
                    <>
                        <p className="admin-muted">
                            Global roles apply everywhere. Give project roles on the Projects tab.
                        </p>
                        <Checklist
                            items={globalRoles.map((role) => ({
                                value: role.name,
                                label: role.title && role.title !== role.name ? `${role.title} (${role.name})` : role.name,
                                detail: role.description ?? `${role.permissions.length} permissions`,
                            }))}
                            selected={groupRoles}
                            onChange={setGroupRoles}
                            placeholder="Search global roles"
                            emptyText="No global roles exist yet."
                        />
                    </>
                )}

                {tab === 'projects' && (
                    <ProjectMembershipEditor
                        value={memberships}
                        onChange={setMemberships}
                        projects={projects}
                        roles={projectRoles}
                        known={group?.projects ?? []}
                        readOnly={!canProjects}
                        readOnlyReason={missingPermission(permissions, ['projects.manage'], 'Changing project roles')}
                        subject="this group"
                    />
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
