import type { PlannedStep, RunOptions, RunOptionsSnapshot } from '../../api/runs.api'

export interface AdvancedState {
    /** Run only steps carrying any of these tags (none: no filter). */
    tags: string[]
    /** Steps the user unticked. */
    excluded: string[]
    /** Steps disabled in the workflow that the user ticked for this run. */
    included: string[]
    /** Step name → node, for steps that run elsewhere than the default node. */
    stepNodes: Record<string, string>
}

export const EMPTY_ADVANCED: AdvancedState = { tags: [], excluded: [], included: [], stepNodes: {} }

/** Whether the step is ticked: enabled and not unticked, or disabled and ticked. */
export function isStepChosen(step: PlannedStep, state: AdvancedState): boolean {
    return step.enabled ? !state.excluded.includes(step.name) : state.included.includes(step.name)
}

export type PlanCheck =
    | { state: 'checking' }
    | { state: 'valid'; plan: RunOptionsSnapshot }
    | { state: 'invalid'; error: string }

/** Request options for the advanced state; empty when nothing was changed. */
export function runOptionsFor(state: AdvancedState, steps: PlannedStep[]): RunOptions {
    const options: RunOptions = {}
    if (state.tags.length) options.tags = state.tags
    if (state.excluded.length || state.included.length) {
        // An explicit list: the server runs a disabled step only when it is named.
        options.steps = steps.filter((step) => isStepChosen(step, state)).map((step) => step.name)
    }
    const overrides = Object.fromEntries(Object.entries(state.stepNodes).filter(([, node]) => node))
    if (Object.keys(overrides).length) options.step_nodes = overrides
    return options
}

/** "local → edge-1 → local" for a plan's segments. */
export function segmentsLabel(plan: RunOptionsSnapshot): string {
    return plan.segments.map((segment) => segment.node).join(' → ')
}

