import type { PlannedStep, RunOptions, RunOptionsSnapshot } from '../../api/runs.api'

export interface AdvancedState {
    /** Run only steps carrying any of these tags (none: no filter). */
    tags: string[]
    /** Steps the user unticked. */
    excluded: string[]
    /** Step name → node, for steps that run elsewhere than the default node. */
    stepNodes: Record<string, string>
}

export const EMPTY_ADVANCED: AdvancedState = { tags: [], excluded: [], stepNodes: {} }

export type PlanCheck =
    | { state: 'checking' }
    | { state: 'valid'; plan: RunOptionsSnapshot }
    | { state: 'invalid'; error: string }

/** Request options for the advanced state; empty when nothing was changed. */
export function runOptionsFor(state: AdvancedState, steps: PlannedStep[]): RunOptions {
    const options: RunOptions = {}
    if (state.tags.length) options.tags = state.tags
    if (state.excluded.length) {
        options.steps = steps.filter((step) => step.enabled && !state.excluded.includes(step.name)).map((step) => step.name)
    }
    const overrides = Object.fromEntries(Object.entries(state.stepNodes).filter(([, node]) => node))
    if (Object.keys(overrides).length) options.step_nodes = overrides
    return options
}

/** "local → edge-1 → local" for a plan's segments. */
export function segmentsLabel(plan: RunOptionsSnapshot): string {
    return plan.segments.map((segment) => segment.node).join(' → ')
}

