import type { ReactNode } from 'react'
import { AlertCircle, Lock } from 'lucide-react'

import type { WidgetState } from './core'
import EntropyLoader from '../../../components/feedback/EntropyLoader'

/** Loading, no-access and error states around a widget's content. */
export function WidgetBody<T>({
    state,
    tool,
    children,
}: {
    state: WidgetState<T>
    tool: string
    children: (data: T) => ReactNode
}) {
    if (state.denied) {
        return (
            <div className="dw-state">
                <Lock size={18} />
                <span>You don't have access to {tool} in this project.</span>
            </div>
        )
    }
    if (state.data === null) {
        if (state.error) {
            return (
                <div className="dw-state dw-state-error" role="alert">
                    <AlertCircle size={18} />
                    <span>{state.error}</span>
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={state.reload}>
                        Retry
                    </button>
                </div>
            )
        }
        return (
            <EntropyLoader size={30} />
        )
    }
    return <>{children(state.data)}</>
}

export function WidgetEmpty({ children }: { children: ReactNode }) {
    return <p className="dw-empty">{children}</p>
}
