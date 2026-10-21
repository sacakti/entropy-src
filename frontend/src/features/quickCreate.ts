import { useEffect, useRef } from 'react'

/** Things the top bar's quick-create menu can start. */
export type CreateTarget =
    | 'plugin'
    | 'workflow'
    | 'vault-entry'
    | 'vault-namespace'
    | 'user'
    | 'group'
    | 'role'
    | 'schedule'
    // Not a create form: the Plugins page's list of bundled plugin updates.
    | 'plugin-updates'

const EVENT = 'entropy:create'

// Survives the page switch: the target page reads it when it mounts.
let pending: CreateTarget | null = null

/** Ask the page owning `target` to open its create form. */
export function requestCreate(target: CreateTarget) {
    pending = target
    window.dispatchEvent(new CustomEvent<CreateTarget>(EVENT, { detail: target }))
}

/** True once if a create was requested for `target` before the page mounted. */
export function consumeCreateIntent(target: CreateTarget): boolean {
    if (pending !== target) return false

    // Cleared after this render: React may run state initializers twice in
    // development, and both runs must see the request.
    window.setTimeout(() => {
        if (pending === target) pending = null
    }, 0)

    return true
}

/** Run `open` when a create is requested while the page is already shown. */
export function useCreateIntent(target: CreateTarget, open: () => void) {
    const latest = useRef(open)

    useEffect(() => {
        latest.current = open
    })

    useEffect(() => {
        function handle(event: Event) {
            if ((event as CustomEvent<CreateTarget>).detail !== target) return
            pending = null
            latest.current()
        }

        window.addEventListener(EVENT, handle)
        return () => window.removeEventListener(EVENT, handle)
    }, [target])
}
