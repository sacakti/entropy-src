import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
    ArchiveRestore,
    Check,
    FileArchive,
    FolderKanban,
    LoaderCircle,
    Pencil,
    Plus,
    RotateCcw,
    Server,
    Trash2,
    UserRound,
    UserRoundPlus,
    UsersRound,
    X,
} from 'lucide-react'

import { adminApi, type AdminRole } from '../../api/admin.api'
import {
    PROJECT_KEY_PATTERN,
    nodeServesProject,
    projectsApi,
    type MemberKind,
    type ProjectMember,
    type ProjectNode,
    type ProjectSummary,
} from '../../api/projects.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import PickerDialog, { type PickerItem } from '../../components/layout/PickerDialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { notifyProjectsUpdated } from '../../services/project'
import { ProjectDumpDialog, ProjectRestoreDialog } from '../transfer/TransferDialogs'
import { AdminPanel, ChipList, EmptyRow, SearchField } from './AdminPanel'
import { errorMessage, formatDate } from './format'
import { defaultProjectRole } from './memberships'
import { missingPermission } from './permissionReason'
import ScopeIntro from './ScopeIntro'
import { usePermissions } from './usePermissions'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

/** Used when the signed-in user may not list roles (e.g. a project maintainer). */
const BUILTIN_PROJECT_ROLES: { name: string; title: string }[] = [
    { name: 'viewer', title: 'Viewer' },
    { name: 'operator', title: 'Operator' },
    { name: 'developer', title: 'Developer' },
    { name: 'maintainer', title: 'Maintainer' },
]

interface RoleOption {
    name: string
    title: string
    description?: string | null
}

/** "Payments Team" → "payments-team". */
function projectKey(name: string): string {
    return name
        .toLowerCase()
        .normalize('NFKD')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 40)
        .replace(/-+$/, '')
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

export default function AdminProjects() {
    const { notify, modal } = useFeedback()
    const permissions = usePermissions()

    const [projects, setProjects] = useState<ProjectSummary[]>([])
    const [canCreate, setCanCreate] = useState(false)
    const [current, setCurrent] = useState<string | null>(null)
    const [roles, setRoles] = useState<AdminRole[] | null>(null)
    const [nodes, setNodes] = useState<ProjectNode[] | null>(null)
    const [nodesError, setNodesError] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [search, setSearch] = useState('')
    const [selected, setSelected] = useState<string | null>(null)
    const [editing, setEditing] = useState<ProjectSummary | 'new' | null>(null)
    const [dumping, setDumping] = useState<ProjectSummary | null>(null)
    const [restoring, setRestoring] = useState<ProjectSummary | null>(null)
    const [deleting, setDeleting] = useState<string | null>(null)
    const searchRef = useRef<HTMLInputElement>(null)

    const load = useCallback(async () => {
        try {
            const [projectList, roleList, nodeList] = await Promise.all([
                projectsApi.list(),
                // Role titles for the member editor; maintainers may not list roles.
                adminApi.roles().catch(() => null),
                projectsApi.nodes().catch((cause: unknown) => {
                    setNodesError(errorMessage(cause, 'Unable to load nodes.'))
                    return null
                }),
            ])
            setProjects(projectList.items)
            setCanCreate(projectList.can_create)
            setCurrent(projectList.current)
            setRoles(roleList?.items ?? null)
            setNodes(nodeList?.items ?? null)
            if (nodeList) setNodesError(null)
            setSelected((key) =>
                key && projectList.items.some((project) => project.key === key)
                    ? key
                    : (projectList.items.find((project) => project.key === projectList.current)?.key ??
                      projectList.items[0]?.key ??
                      null),
            )
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load projects.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        // Load after mount; `load` only sets state once its requests settle.
        Promise.resolve().then(load)
    }, [load])

    const projectRoles: RoleOption[] = useMemo(() => {
        if (roles) {
            return roles
                .filter((role) => role.scope === 'project')
                .map((role) => ({ name: role.name, title: role.title || role.name, description: role.description }))
        }
        return BUILTIN_PROJECT_ROLES
    }, [roles])

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase()

        return needle
            ? projects.filter((project) =>
                  [project.key, project.name, project.description, ...project.my_roles]
                      .join(' ')
                      .toLowerCase()
                      .includes(needle),
              )
            : projects
    }, [projects, search])

    const manageReason = missingPermission(permissions, ['projects.manage'], 'Changing projects')
    const createReason = canCreate ? null : (manageReason ?? 'You may not create projects.')
    const project = projects.find((item) => item.key === selected) ?? null

    const remove = async (target: ProjectSummary) => {
        const confirmed = await modal.confirm({
            title: `Delete project ${target.name}?`,
            message: `Its ${plural(target.members, 'member')} lose access. Projects that still hold workflows or schedules cannot be deleted. This cannot be undone.`,
            confirmText: 'Delete project',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setDeleting(target.key)

        try {
            await projectsApi.remove(target.key)
            setProjects((items) => items.filter((item) => item.key !== target.key))
            if (selected === target.key) setSelected(null)
            notify.success(`Project '${target.name}' deleted.`)
            notifyProjectsUpdated()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the project.'))
        } finally {
            setDeleting(null)
        }
    }

    const openCreate = () => {
        if (canCreate) setEditing('new')
    }

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
                title="Projects"
                count={projects.length}
                subtitle="Each project has its own workflows, schedules, drafts and runs, and its own members."
                error={error}
                refreshing={refreshing || loading}
                onRefresh={() => {
                    setRefreshing(true)
                    void load()
                }}
                actions={
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary entropy-button-icon"
                        aria-label="Create project"
                        title={createReason ?? 'Create project (Ctrl+N)'}
                        onClick={openCreate}
                        disabled={!canCreate}
                    >
                        <Plus size={20} />
                    </button>
                }
                toolbar={
                    <SearchField
                        inputRef={searchRef}
                        value={search}
                        onChange={setSearch}
                        placeholder="Search projects…"
                    />
                }
            >
                <ScopeIntro />

                <div className="list-table-wrap">
                    <table className="list-table admin-project-table">
                        <thead>
                            <tr>
                                <th>Project</th>
                                <th>Workflows</th>
                                <th>Schedules</th>
                                <th>Members</th>
                                <th>My roles</th>
                                <th className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && projects.length === 0 ? (
                                <EmptyRow colSpan={6} title="Loading projects…" text="Fetching projects." />
                            ) : filtered.length === 0 ? (
                                <EmptyRow
                                    colSpan={6}
                                    title={search ? 'No projects match' : 'No projects'}
                                    text={search ? 'Try a different search.' : 'Create a project to get started.'}
                                />
                            ) : (
                                filtered.map((item) => (
                                    <tr
                                        key={item.key}
                                        className={`admin-row-selectable${item.key === selected ? ' is-selected' : ''}`}
                                        onClick={() => setSelected(item.key)}
                                        aria-selected={item.key === selected}
                                    >
                                        <td>
                                            <div className="list-name">
                                                <span className="list-name-icon" aria-hidden="true">
                                                    <FolderKanban size={16} />
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>
                                                        <button
                                                            type="button"
                                                            className="admin-link-button"
                                                            onClick={(event) => {
                                                                event.stopPropagation()
                                                                setSelected(item.key)
                                                            }}
                                                        >
                                                            {item.name}
                                                        </button>
                                                        {item.key === current && <span className="admin-badge">Current</span>}
                                                    </strong>
                                                    <span>
                                                        <code className="admin-role-name">{item.key}</code>
                                                        {item.description ? ` · ${item.description}` : ''}
                                                    </span>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="list-cell-text">{item.workflows}</td>
                                        <td className="list-cell-text">{item.schedules}</td>
                                        <td className="list-cell-text">{item.members}</td>
                                        <td>
                                            <ChipList
                                                values={item.my_roles.map(
                                                    (name) => projectRoles.find((role) => role.name === name)?.title ?? name,
                                                )}
                                                tone="accent"
                                                empty="None"
                                            />
                                        </td>
                                        <td>
                                            <div className="list-operations" onClick={(event) => event.stopPropagation()}>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Dump ${item.name}`}
                                                    title="Download a dump (workflows, schedules, plugins, vault)"
                                                    onClick={() => setDumping(item)}
                                                >
                                                    <FileArchive size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Restore into ${item.name}`}
                                                    title="Restore a dump into this project"
                                                    onClick={() => setRestoring(item)}
                                                >
                                                    <ArchiveRestore size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Edit ${item.name}`}
                                                    title={manageReason ?? 'Edit'}
                                                    disabled={Boolean(manageReason)}
                                                    onClick={() => setEditing(item)}
                                                >
                                                    <Pencil size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                    aria-label={`Delete ${item.name}`}
                                                    title={
                                                        item.key === 'default'
                                                            ? 'The Default project cannot be deleted'
                                                            : (manageReason ?? 'Delete')
                                                    }
                                                    disabled={
                                                        item.key === 'default' ||
                                                        Boolean(manageReason) ||
                                                        deleting === item.key
                                                    }
                                                    onClick={() => void remove(item)}
                                                >
                                                    {deleting === item.key ? (
                                                        <LoaderCircle size={15} className="entropy-spin" />
                                                    ) : (
                                                        <Trash2 size={15} />
                                                    )}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </AdminPanel>

            {project && (
                <ProjectDetail
                    key={project.key}
                    project={project}
                    roles={projectRoles}
                    nodes={nodes}
                    nodesError={nodesError}
                    onMembersSaved={(count) =>
                        setProjects((items) =>
                            items.map((item) => (item.key === project.key ? { ...item, members: count } : item)),
                        )
                    }
                />
            )}

            {dumping && <ProjectDumpDialog project={dumping} onClose={() => setDumping(null)} />}
            {restoring && (
                <ProjectRestoreDialog
                    project={restoring}
                    onClose={() => setRestoring(null)}
                    onDone={() => void load()}
                />
            )}

            {editing && (
                <ProjectDialog
                    project={editing === 'new' ? null : editing}
                    taken={projects.map((item) => item.key)}
                    onClose={() => setEditing(null)}
                    onSaved={(key) => {
                        setEditing(null)
                        setSelected(key)
                        void load()
                    }}
                />
            )}
        </div>
    )
}

interface DraftMember {
    kind: MemberKind
    name: string
    full_name: string | null
    role: string
}

const memberKey = (member: { kind: MemberKind; name: string; role: string }) =>
    `${member.kind}\u0000${member.name}\u0000${member.role}`

function sameMembers(first: DraftMember[], second: DraftMember[]): boolean {
    const keys = (list: DraftMember[]) => [...new Set(list.map(memberKey))].sort().join('\n')
    return keys(first) === keys(second)
}

function toDraft(members: ProjectMember[]): DraftMember[] {
    return members.map(({ kind, name, full_name, role }) => ({ kind, name, full_name, role }))
}

/** Members and node access of one project. */
function ProjectDetail({
    project,
    roles: knownRoles,
    nodes,
    nodesError,
    onMembersSaved,
}: {
    project: ProjectSummary
    roles: RoleOption[]
    nodes: ProjectNode[] | null
    nodesError: string | null
    onMembersSaved: (count: number) => void
}) {
    const { notify } = useFeedback()
    const [saved, setSaved] = useState<ProjectMember[] | null>(null)
    const [draft, setDraft] = useState<DraftMember[]>([])
    const [canManage, setCanManage] = useState(project.can_manage_members)
    const [loadError, setLoadError] = useState<string | null>(null)
    useErrorToast(loadError)
    const [saveError, setSaveError] = useState<string | null>(null)
    useErrorToast(saveError)
    const [saving, setSaving] = useState(false)
    const [picking, setPicking] = useState(false)
    const directory = useRef<Promise<PickerItem[]> | null>(null)
    // Roles a maintainer may give, custom ones included (they cannot list all roles).
    const [assignableRoles, setAssignableRoles] = useState<RoleOption[] | null>(null)
    const roles = assignableRoles ?? knownRoles

    useEffect(() => {
        let active = true

        projectsApi
            .members(project.key)
            .then((result) => {
                if (!active) return
                setSaved(result.members)
                setDraft(toDraft(result.members))
                setCanManage(result.can_manage)
                if (result.can_manage) {
                    projectsApi
                        .assignable(project.key)
                        .then((found) => {
                            if (active && found.roles.length) setAssignableRoles(found.roles)
                        })
                        .catch(() => undefined)
                }
                setLoadError(null)
            })
            .catch((cause: unknown) => {
                if (active) setLoadError(errorMessage(cause, 'Unable to load the members.'))
            })

        return () => {
            active = false
        }
    }, [project.key])

    const dirty = saved !== null && !sameMembers(draft, toDraft(saved))
    const roleTitle = (name: string) => roles.find((role) => role.name === name)?.title ?? name
    const roleChoices = (current: string) =>
        roles.some((role) => role.name === current) ? roles : [...roles, { name: current, title: roleTitle(current) }]

    const loadDirectory = () => {
        directory.current ??= projectsApi
            .assignable(project.key)
            .catch(() => ({ users: [], groups: [], roles: [] }))
            .then(({ users, groups }) => [
                ...users.map((user) => ({
                    id: `user:${user.username}`,
                    label: user.full_name ? `${user.full_name} (@${user.username})` : user.username,
                    detail: 'User',
                })),
                ...groups.map((group) => ({
                    id: `group:${group.name}`,
                    label: group.name,
                    detail: `Group · ${plural(group.members, 'member')}`,
                })),
            ])
        return directory.current
    }

    const pickerItems = async (query: string): Promise<PickerItem[]> => {
        const all = await loadDirectory()
        const needle = query.toLowerCase()
        const matches = all.filter((item) => !needle || `${item.label} ${item.id}`.toLowerCase().includes(needle))

        // Without permission to list users and groups, add a member by exact name.
        if (all.length === 0 && query) {
            return [
                { id: `user:${query}`, label: query, detail: 'Add as a user by name' },
                { id: `group:${query}`, label: query, detail: 'Add as a group by name' },
            ]
        }

        return matches.slice(0, 50)
    }

    const addMember = (item: PickerItem) => {
        const separator = item.id.indexOf(':')
        const kind = item.id.slice(0, separator) as MemberKind
        const name = item.id.slice(separator + 1)
        const role = defaultProjectRole(roles)
        const existing = draft.filter((member) => member.kind === kind && member.name === name)

        if (existing.some((member) => member.role === role)) {
            notify.info(`${name} is already a ${roleTitle(role)} here.`)
            return
        }

        setDraft((members) => [...members, { kind, name, full_name: null, role }])
    }

    const save = async () => {
        if (saving) return

        setSaving(true)
        setSaveError(null)

        try {
            const unique = draft.filter(
                (member, index) => draft.findIndex((other) => memberKey(other) === memberKey(member)) === index,
            )
            const result = await projectsApi.setMembers(
                project.key,
                unique.map(({ kind, name, role }) => ({ kind, name, role })),
            )
            setSaved(result.members)
            // Your own roles may have changed: the switcher shows them.
            notifyProjectsUpdated()
            setDraft(toDraft(result.members))
            onMembersSaved(result.members.length)
            notify.success(`Members of '${project.name}' saved.`)
        } catch (cause) {
            setSaveError(errorMessage(cause, 'Unable to save the members.'))
        } finally {
            setSaving(false)
        }
    }

    const usable = nodes?.filter((node) => nodeServesProject(node, project.key)) ?? []

    return (
        <section className="dashboard-section list-section admin-project-detail" aria-label={`${project.name} details`}>
            <div className="dashboard-section-heading list-section-heading">
                <div>
                    <h2>
                        <FolderKanban size={18} aria-hidden="true" />
                        {project.name}
                        <code className="admin-role-name">{project.key}</code>
                    </h2>
                    <p>{project.description || 'No description'}</p>
                </div>
            </div>

            <div className="admin-project-grid">
                <div className="admin-project-card">
                    <header>
                        <div>
                            <h3>Members</h3>
                            <p className="admin-muted">
                                Users and groups given a project role here. Their role decides what they may do with
                                this project’s workflows, schedules and runs.
                            </p>
                        </div>
                        {canManage && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => setPicking(true)}
                                disabled={saved === null}
                            >
                                <UserRoundPlus size={14} />
                                Add member
                            </button>
                        )}
                    </header>

                    {loadError ? (
                        <p className="entropy-unavailable">Not available.</p>
                    ) : saved === null ? (
                        <EntropyLoader inline label="Loading members…" />
                    ) : draft.length === 0 ? (
                        <p className="admin-checklist-empty">
                            No members yet.{canManage ? ' Add users or groups to give them access.' : ''}
                        </p>
                    ) : (
                        <ul className="admin-member-list" role="list">
                            {draft.map((member, index) => (
                                <li key={`${memberKey(member)}:${index}`} className="admin-member-row">
                                    <span className="admin-member-icon" aria-hidden="true">
                                        {member.kind === 'group' ? <UsersRound size={15} /> : <UserRound size={15} />}
                                    </span>
                                    <span className="admin-member-name">
                                        <strong>{member.full_name || member.name}</strong>
                                        <small>
                                            {member.kind === 'group' ? 'Group' : `@${member.name}`}
                                        </small>
                                    </span>
                                    {canManage ? (
                                        <select
                                            className="entropy-select"
                                            aria-label={`Role of ${member.name}`}
                                            value={member.role}
                                            onChange={(event) =>
                                                setDraft((members) =>
                                                    members.map((item, position) =>
                                                        position === index ? { ...item, role: event.target.value } : item,
                                                    ),
                                                )
                                            }
                                        >
                                            {roleChoices(member.role).map((role) => (
                                                <option key={role.name} value={role.name}>
                                                    {role.title}
                                                </option>
                                            ))}
                                        </select>
                                    ) : (
                                        <span className="admin-chip is-accent">{roleTitle(member.role)}</span>
                                    )}
                                    {canManage && (
                                        <button
                                            type="button"
                                            className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                            aria-label={`Remove ${member.name}`}
                                            title="Remove"
                                            onClick={() =>
                                                setDraft((members) => members.filter((_, position) => position !== index))
                                            }
                                        >
                                            <X size={15} />
                                        </button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}

                    {!canManage && saved !== null && (
                        <p className="admin-muted">
                            Only this project’s maintainers and administrators with projects.manage can change its members.
                        </p>
                    )}


                    {canManage && (
                        <footer>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary"
                                disabled={!dirty || saving}
                                onClick={() => {
                                    if (saved) setDraft(toDraft(saved))
                                    setSaveError(null)
                                }}
                            >
                                <RotateCcw size={15} />
                                Discard
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-primary"
                                disabled={!dirty || saving}
                                onClick={() => void save()}
                            >
                                {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Check size={15} />}
                                Save members
                            </button>
                        </footer>
                    )}
                </div>

                <div className="admin-project-card">
                    <header>
                        <div>
                            <h3>Nodes</h3>
                            <p className="admin-muted">Where this project’s workflows may run.</p>
                        </div>
                    </header>

                    {nodes === null ? (
                        nodesError ? <p className="admin-checklist-empty">{nodesError}</p> : <EntropyLoader inline label="Loading nodes…" />
                    ) : usable.length === 0 ? (
                        <p className="admin-checklist-empty">No node serves this project yet.</p>
                    ) : (
                        <ul className="admin-member-list" role="list">
                            {usable.map((node) => (
                                <li key={node.name} className="admin-member-row is-node">
                                    <span className="admin-member-icon" aria-hidden="true">
                                        <Server size={15} />
                                    </span>
                                    <span className="admin-member-name">
                                        <strong>{node.name}</strong>
                                        <small>
                                            {[node.kind, node.host, node.enabled ? null : 'disabled']
                                                .filter(Boolean)
                                                .join(' · ')}
                                        </small>
                                    </span>
                                    <span className={`admin-chip${node.access.scope === 'shared' ? '' : ' is-accent'}`}>
                                        {node.access.scope === 'shared' ? 'All projects' : 'Assigned'}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}

                    <p className="admin-muted">
                        Node administrators share nodes with every project or assign them to some on the Nodes page.
                    </p>
                </div>
            </div>

            {picking && (
                <PickerDialog
                    title={`Add a member to ${project.name}`}
                    subtitle="Pick a user or group; choose its role in the list afterwards."
                    icon={<UserRoundPlus size={18} />}
                    placeholder="Search users and groups…"
                    empty="No users or groups match. Type an exact name to add one."
                    load={pickerItems}
                    onPick={addMember}
                    onClose={() => setPicking(false)}
                />
            )}
        </section>
    )
}

function ProjectDialog({
    project,
    taken,
    onClose,
    onSaved,
}: {
    project: ProjectSummary | null
    taken: string[]
    onClose: () => void
    onSaved: (key: string) => void
}) {
    const { notify } = useFeedback()
    const creating = project === null

    const [name, setName] = useState(project?.name ?? '')
    const [key, setKey] = useState(project?.key ?? '')
    const [keyTouched, setKeyTouched] = useState(!creating)
    const [description, setDescription] = useState(project?.description ?? '')
    const [saving, setSaving] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)
    useErrorToast(formError)

    const keyProblem = !creating
        ? null
        : !key
          ? null
          : !PROJECT_KEY_PATTERN.test(key)
            ? 'Use 1–40 lowercase letters, digits and dashes.'
            : taken.includes(key)
              ? 'Another project already uses this key.'
              : null

    const dirty =
        creating || name.trim() !== project.name || description.trim() !== (project.description ?? '')

    const save = async (event?: FormEvent) => {
        event?.preventDefault()

        if (saving) return

        setSaving(true)
        setFormError(null)

        try {
            if (!name.trim()) throw new Error('Enter a project name.')

            if (creating) {
                if (!key || keyProblem) throw new Error(keyProblem ?? 'Enter a project key.')
                const created = await projectsApi.create({ key, name: name.trim(), description: description.trim() })
                notify.success(`Project '${created.name}' created.`)
                notifyProjectsUpdated()
                onSaved(created.key)
            } else {
                await projectsApi.update(project.key, { name: name.trim(), description: description.trim() })
                notify.success(`Project '${name.trim()}' updated.`)
                notifyProjectsUpdated()
                onSaved(project.key)
            }
        } catch (cause) {
            setFormError(errorMessage(cause, 'Unable to save the project.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={creating ? 'Create project' : `Edit ${project.name}`}
            subtitle={
                creating
                    ? 'A project holds its own workflows, schedules and runs. Add members after creating it.'
                    : `Key ${project.key} · created ${formatDate(project.created_at)}`
            }
            icon={<FolderKanban size={18} />}
            onClose={onClose}
            className="admin-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="submit"
                        form="admin-project-form"
                        className="entropy-button entropy-button-primary"
                        disabled={saving || !dirty || Boolean(keyProblem)}
                    >
                        {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Check size={15} />}
                        {creating ? 'Create project' : 'Save changes'}
                    </button>
                </>
            }
        >
            <form id="admin-project-form" className="admin-form" onSubmit={save}>
                <div className="admin-form-grid">
                    <label className="admin-field">
                        <span>Name</span>
                        <input
                            value={name}
                            onChange={(event) => {
                                setName(event.target.value)
                                if (!keyTouched) setKey(projectKey(event.target.value))
                            }}
                            placeholder="e.g. Payments"
                            maxLength={100}
                            required
                        />
                    </label>
                    <label className="admin-field">
                        <span>Key</span>
                        <input
                            value={key}
                            onChange={(event) => {
                                setKeyTouched(true)
                                setKey(event.target.value.toLowerCase())
                            }}
                            placeholder="e.g. payments"
                            disabled={!creating}
                            maxLength={40}
                            spellCheck={false}
                            required
                            aria-invalid={Boolean(keyProblem)}
                        />
                        <small>{keyProblem ?? (creating ? 'Used in URLs and the ent CLI; cannot be changed later.' : 'The key cannot be changed.')}</small>
                    </label>
                    <label className="admin-field admin-field-wide">
                        <span>Description</span>
                        <textarea
                            value={description}
                            onChange={(event) => setDescription(event.target.value)}
                            placeholder="What is this project for?"
                            maxLength={500}
                            rows={3}
                        />
                    </label>
                </div>
            </form>

        </Dialog>
    )
}
