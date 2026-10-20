import { useState } from 'react'
import { ListChecks, Server, SkipForward, Tag, Variable } from 'lucide-react'

import type { RunOptionsSnapshot } from '../../api/runs.api'

const SHOWN = 2

const SKIP_REASONS: Record<string, string> = {
    disabled: 'disabled',
    'tag filter': 'tag filter',
    'not selected': 'deselected',
}

/** A list that shows its first items and expands on request. */
function Collapsed({ items, render }: { items: string[]; render?: (item: string) => string }) {
    const [all, setAll] = useState(false)
    const shown = all ? items : items.slice(0, SHOWN)
    const hidden = items.length - shown.length
    return (
        <>
            {shown.map((item) => (
                <span key={item} className="run-tag">
                    {render ? render(item) : item}
                </span>
            ))}
            {hidden > 0 && (
                <button type="button" className="run-options-more" onClick={() => setAll(true)}>
                    +{hidden} more
                </button>
            )}
            {all && items.length > SHOWN && (
                <button type="button" className="run-options-more" onClick={() => setAll(false)}>
                    show less
                </button>
            )}
        </>
    )
}

/** What this run was started with: tag filter, steps, skipped steps, nodes. */
export default function RunOptionsSummary({ options }: { options: RunOptionsSnapshot }) {
    const reasons = new Map(options.steps.map((step) => [step.name, step.skip_reason ?? null]))
    const everything = options.skipped.every((name) => reasons.get(name) === 'disabled')

    return (
        <dl className="run-options" aria-label="Run options">
            {options.tags.length > 0 && (
                <div>
                    <dt>
                        <Tag size={13} aria-hidden="true" /> Tags
                    </dt>
                    <dd>
                        <Collapsed items={options.tags} />
                    </dd>
                </div>
            )}
            <div>
                <dt>
                    <ListChecks size={13} aria-hidden="true" /> Steps
                </dt>
                <dd>
                    {everything ? (
                        <span className="run-options-plain">All {options.selected.length}</span>
                    ) : (
                        <Collapsed items={options.selected} />
                    )}
                </dd>
            </div>
            {options.skipped.length > 0 && (
                <div>
                    <dt>
                        <SkipForward size={13} aria-hidden="true" /> Skipped
                    </dt>
                    <dd>
                        <Collapsed
                            items={options.skipped}
                            render={(name) => {
                                const reason = reasons.get(name)
                                return reason ? `${name} (${SKIP_REASONS[reason] ?? reason})` : name
                            }}
                        />
                    </dd>
                </div>
            )}
            {options.segments.length > 1 && (
                <div>
                    <dt>
                        <Server size={13} aria-hidden="true" /> Nodes
                    </dt>
                    <dd>
                        <span className="run-options-plain">
                            {options.segments.map((segment) => segment.node).join(' → ')}
                        </span>
                    </dd>
                </div>
            )}
            {options.variables.length > 0 && (
                <div>
                    <dt>
                        <Variable size={13} aria-hidden="true" /> Inputs
                    </dt>
                    <dd>
                        <Collapsed items={options.variables} />
                    </dd>
                </div>
            )}
        </dl>
    )
}
