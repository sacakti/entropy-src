/**
 * Why an action is unavailable to the signed-in user, or null when it is
 * allowed. Nothing is blocked while permissions are still loading.
 */
export function missingPermission(
    permissions: Set<string> | null,
    needed: string[],
    action: string,
): string | null {
    if (!permissions) return null
    const lacking = needed.filter((permission) => !permissions.has(permission))
    return lacking.length ? `No permission: ${action} needs ${lacking.join(' and ')}.` : null
}
