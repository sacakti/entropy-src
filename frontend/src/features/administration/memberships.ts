import type { MembershipInput, ProjectMembership } from '../../api/admin.api'

/** "Developer in Payments" for each membership, for compact lists. */
export function membershipLabels(memberships: ProjectMembership[]): string[] {
    return memberships.map((membership) => `${membership.role_title} in ${membership.project_name}`)
}

export function toMembershipInputs(memberships: ProjectMembership[]): MembershipInput[] {
    return memberships.map(({ project, role }) => ({ project, role }))
}

/** Drop rows that repeat the same project and role. */
export function uniqueMemberships(memberships: MembershipInput[]): MembershipInput[] {
    const seen = new Set<string>()

    return memberships.filter((membership) => {
        const key = `${membership.project}\u0000${membership.role}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
    })
}

export function sameMemberships(first: MembershipInput[], second: MembershipInput[]): boolean {
    const keys = (list: MembershipInput[]) =>
        uniqueMemberships(list)
            .map((membership) => `${membership.project}\u0000${membership.role}`)
            .sort()
            .join('\n')

    return keys(first) === keys(second)
}

/** The role to offer first for a new membership: Viewer when it exists. */
export function defaultProjectRole(roles: { name: string }[]): string {
    return roles.find((role) => role.name === 'viewer')?.name ?? roles[0]?.name ?? 'viewer'
}
