import { FolderKanban, Plus, X } from 'lucide-react'

import type { AdminRole, MembershipInput, ProjectMembership } from '../../api/admin.api'
import type { ProjectSummary } from '../../api/projects.api'
import { defaultProjectRole, uniqueMemberships } from './memberships'

/**
 * Edit the (project, project role) pairs of one user or group. The caller
 * saves them with `/users/{name}/projects` or `/groups/{name}/projects`.
 */
export function ProjectMembershipEditor({
    value,
    onChange,
    projects,
    roles,
    known,
    readOnly,
    readOnlyReason,
    subject,
}: {
    value: MembershipInput[]
    onChange: (value: MembershipInput[]) => void
    projects: ProjectSummary[]
    /** Project-scope roles. */
    roles: AdminRole[]
    /** The saved memberships, so names show even for projects or roles not listed. */
    known: ProjectMembership[]
    readOnly?: boolean
    readOnlyReason?: string | null
    /** "this user" or "this group". */
    subject: string
}) {
    const projectName = (key: string) =>
        projects.find((project) => project.key === key)?.name ??
        known.find((membership) => membership.project === key)?.project_name ??
        key
    const roleTitle = (name: string) =>
        roles.find((role) => role.name === name)?.title ??
        known.find((membership) => membership.role === name)?.role_title ??
        name

    const projectOptions = [
        ...projects.map((project) => ({ value: project.key, label: project.name })),
        ...value
            .filter((membership) => !projects.some((project) => project.key === membership.project))
            .map((membership) => ({ value: membership.project, label: projectName(membership.project) })),
    ].filter((option, index, all) => all.findIndex((other) => other.value === option.value) === index)

    const roleOptions = (current: string) => [
        ...roles.map((role) => ({ value: role.name, label: role.title || role.name })),
        ...(roles.some((role) => role.name === current) ? [] : [{ value: current, label: roleTitle(current) }]),
    ]

    const update = (index: number, change: Partial<MembershipInput>) =>
        onChange(value.map((membership, position) => (position === index ? { ...membership, ...change } : membership)))

    const add = () => {
        const used = new Set(value.map((membership) => membership.project))
        const project = projects.find((item) => !used.has(item.key)) ?? projects[0]
        if (!project) return
        onChange([...value, { project: project.key, role: defaultProjectRole(roles) }])
    }

    const duplicates = value.length - uniqueMemberships(value).length

    if (readOnly) {
        return (
            <div className="admin-memberships">
                {value.length === 0 ? (
                    <p className="admin-checklist-empty">{`No project roles are given to ${subject} directly.`}</p>
                ) : (
                    <ul className="admin-membership-list" role="list">
                        {value.map((membership) => (
                            <li key={`${membership.project}:${membership.role}`} className="admin-membership-row is-readonly">
                                <FolderKanban size={15} aria-hidden="true" />
                                <span>
                                    <strong>{projectName(membership.project)}</strong>
                                    <small>{membership.project}</small>
                                </span>
                                <span className="admin-chip is-accent">{roleTitle(membership.role)}</span>
                            </li>
                        ))}
                    </ul>
                )}
                {readOnlyReason && <p className="admin-muted">{readOnlyReason}</p>}
            </div>
        )
    }

    return (
        <div className="admin-memberships">
            <p className="admin-muted">
                {`Project roles give ${subject} access to one project's workflows, schedules and runs.`}
            </p>

            {value.length === 0 ? (
                <p className="admin-checklist-empty">{`${subject[0].toUpperCase()}${subject.slice(1)} is not in any project yet.`}</p>
            ) : (
                <ul className="admin-membership-list" role="list">
                    {value.map((membership, index) => (
                        <li key={index} className="admin-membership-row">
                            <label className="admin-membership-field">
                                <span>Project</span>
                                <select
                                    className="entropy-select"
                                    value={membership.project}
                                    onChange={(event) => update(index, { project: event.target.value })}
                                >
                                    {projectOptions.map((option) => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <label className="admin-membership-field">
                                <span>Role</span>
                                <select
                                    className="entropy-select"
                                    value={membership.role}
                                    onChange={(event) => update(index, { role: event.target.value })}
                                >
                                    {roleOptions(membership.role).map((option) => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <button
                                type="button"
                                className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                aria-label={`Remove ${roleTitle(membership.role)} in ${projectName(membership.project)}`}
                                title="Remove"
                                onClick={() => onChange(value.filter((_, position) => position !== index))}
                            >
                                <X size={15} />
                            </button>
                        </li>
                    ))}
                </ul>
            )}

            {duplicates > 0 && (
                <p className="admin-muted">Repeated project and role pairs are saved once.</p>
            )}

            <div>
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary entropy-button-sm"
                    onClick={add}
                    disabled={projects.length === 0 || roles.length === 0}
                    title={projects.length === 0 ? 'No projects to choose from' : undefined}
                >
                    <Plus size={14} />
                    Add to project
                </button>
            </div>
        </div>
    )
}
