import { useEffect, useState } from 'react'

import { getCurrentUser } from '../../services/auth'

/**
 * The signed-in user's effective permissions, so pages can hide actions the
 * server would refuse. `null` while loading.
 */
export function usePermissions(): Set<string> | null {
    const [permissions, setPermissions] = useState<Set<string> | null>(null)

    useEffect(() => {
        let active = true

        getCurrentUser()
            .then((result) => {
                if (active) setPermissions(new Set(result.permissions))
            })
            .catch(() => {
                if (active) setPermissions(new Set())
            })

        return () => {
            active = false
        }
    }, [])

    return permissions
}
