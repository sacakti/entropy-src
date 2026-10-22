import { Component, Suspense, useRef, useState, type ErrorInfo, type ReactNode } from 'react'
import { AlertCircle, ChevronLeft, LoaderCircle, Search, Wrench, X } from 'lucide-react'

import { TOOLS, findTool, matchesTool, type ToolDefinition } from './registry'
import '../../styles/tools.css'

/** Keeps a failing tool (e.g. a chunk that cannot load) from blanking the page. */
class ToolBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
    state: { error: Error | null } = { error: null }

    static getDerivedStateFromError(error: Error) {
        return { error }
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error('Tool failed to render', error, info.componentStack)
    }

    render() {
        if (this.state.error) {
            return (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>
                        This tool could not be opened: {this.state.error.message}. Reload the page and try again.
                    </span>
                </div>
            )
        }

        return this.props.children
    }
}

function ToolCard({ tool, onOpen }: { tool: ToolDefinition; onOpen: (tool: ToolDefinition) => void }) {
    const Icon = tool.icon

    return (
        <li>
            <button type="button" className="tools-card" onClick={() => onOpen(tool)}>
                <span className="tools-card-icon" aria-hidden="true">
                    <Icon size={26} strokeWidth={1.75} />
                </span>
                <span className="tools-card-text">
                    <strong>{tool.name}</strong>
                    <span>{tool.description}</span>
                </span>
            </button>
        </li>
    )
}

function ToolView({ tool, onBack }: { tool: ToolDefinition; onBack: () => void }) {
    const Icon = tool.icon
    const ToolComponent = tool.component

    return (
        <section className="dashboard-section tools-view" aria-labelledby="tools-view-title">
            <div className="tools-view-heading">
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-sm"
                    onClick={onBack}
                >
                    <ChevronLeft size={15} /> All tools
                </button>
                <span className="tools-view-title">
                    <span className="tools-card-icon tools-card-icon-sm" aria-hidden="true">
                        <Icon size={17} strokeWidth={1.9} />
                    </span>
                    <h2 id="tools-view-title">{tool.name}</h2>
                </span>
            </div>
            <ToolBoundary key={tool.id}>
                <Suspense
                    fallback={
                        <div className="tools-empty" role="status">
                            <LoaderCircle size={20} className="entropy-spin" aria-hidden="true" />
                            <strong>Loading {tool.name.toLowerCase()}…</strong>
                        </div>
                    }
                >
                    <ToolComponent />
                </Suspense>
            </ToolBoundary>
        </section>
    )
}

/**
 * Tools page: an app-launcher gallery of browser-side utilities, and the
 * opened tool shown full width. Tools come from `registry.ts`.
 */
export default function Tools({
    initialTool,
    onToolChange,
}: {
    /** Tool id to open first (e.g. restored from the URL). Unknown ids show the gallery. */
    initialTool?: string
    /** Called with the opened tool's id, or null when returning to the gallery. */
    onToolChange?: (id: string | null) => void
}) {
    const [activeId, setActiveId] = useState<string | null>(() => findTool(initialTool)?.id ?? null)
    const [seenInitial, setSeenInitial] = useState(initialTool)
    const [query, setQuery] = useState('')
    const searchRef = useRef<HTMLInputElement>(null)

    // Follow later changes of initialTool (e.g. browser back/forward).
    if (initialTool !== seenInitial) {
        setSeenInitial(initialTool)
        setActiveId(findTool(initialTool)?.id ?? null)
    }

    const active = findTool(activeId)
    const matches = TOOLS.filter((tool) => matchesTool(tool, query))

    const open = (id: string | null) => {
        setActiveId(id)
        onToolChange?.(id)
    }

    if (active) {
        return (
            <section className="list-page tools-page">
                <ToolView tool={active} onBack={() => open(null)} />
            </section>
        )
    }

    return (
        <section className="list-page tools-page">
            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Tools
                            <span className="list-count" aria-label={`${TOOLS.length} tools`}>
                                {TOOLS.length}
                            </span>
                        </h2>
                        <p>
                            Everyday utilities. The compare tools run in your browser and never upload what you
                            compare; EagleAPI sends requests from the Entropy server.
                        </p>
                    </div>
                </div>

                <div className="list-toolbar">
                    <div className="list-search">
                        <Search size={17} aria-hidden="true" />
                        <input
                            ref={searchRef}
                            type="search"
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            onKeyDown={(event) => {
                                // Enter opens the only match.
                                if (event.key === 'Enter' && matches.length === 1) open(matches[0].id)
                            }}
                            placeholder="Search tools..."
                            aria-label="Search tools"
                        />
                        {query && (
                            <button
                                type="button"
                                aria-label="Clear search"
                                onClick={() => {
                                    setQuery('')
                                    searchRef.current?.focus()
                                }}
                            >
                                <X size={15} />
                            </button>
                        )}
                    </div>
                </div>

                {matches.length > 0 ? (
                    <ul className="tools-grid" aria-label="Tools">
                        {matches.map((tool) => (
                            <ToolCard key={tool.id} tool={tool} onOpen={(item) => open(item.id)} />
                        ))}
                    </ul>
                ) : (
                    <div className="tools-empty">
                        <Wrench size={22} aria-hidden="true" />
                        <strong>No tools found</strong>
                        <p>No tool matches “{query.trim()}”. Try another word or clear the search.</p>
                    </div>
                )}
            </section>
        </section>
    )
}
