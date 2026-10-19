import { useState } from 'react'
import {
    ChevronDown,
    Info,
    PanelLeftClose,
    PanelLeftOpen,
} from 'lucide-react'

import {
    navigation,
    type PageId,
} from '../../types/navigation'
import EntropyLogo from './EntropyLogo'

interface SidebarProps {
    activePage: PageId
    collapsed: boolean
    onPageChange: (page: PageId) => void
    onToggleCollapse: () => void
    version: string
}

export default function Sidebar({
    activePage,
    collapsed,
    onPageChange,
    onToggleCollapse,
    version,
}: SidebarProps) {
    // Sections the user closed; a section holding the current page stays open.
    const [closed, setClosed] = useState<Set<PageId>>(new Set())

    return (
        <aside
            className={`entropy-sidebar ${collapsed ? 'collapsed' : ''}`}
        >
            <div className="entropy-sidebar-brand">
                <EntropyLogo size={38} />

                {!collapsed && (
                    <div className="entropy-brand-copy">
                        <strong>Entropy</strong>
                        <span>DEPLOYMENT PLATFORM</span>
                    </div>
                )}
            </div>

            <button
                className="sidebar-collapse"
                type="button"
                onClick={onToggleCollapse}
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
                {collapsed
                    ? <PanelLeftOpen size={18} />
                    : <PanelLeftClose size={18} />}
            </button>

            <div className="sidebar-section-label">
                {!collapsed && 'WORKSPACE'}
            </div>

            <nav
                className="entropy-navigation"
                aria-label="Main navigation"
            >
                {navigation.map(({ id, label, icon: Icon, children }) => {
                    const childActive = children?.some((child) => child.id === activePage) ?? false
                    const expanded = Boolean(children) && (childActive || activePage === id) && !closed.has(id)

                    return (
                        <div key={id} className="nav-group">
                            <button
                                type="button"
                                className={`nav-item ${activePage === id ? 'active' : ''} ${
                                    childActive ? 'has-active-child' : ''
                                }`}
                                onClick={() => {
                                    if (children && (activePage === id || childActive)) {
                                        setClosed((current) => {
                                            const next = new Set(current)
                                            if (next.has(id)) next.delete(id)
                                            else next.add(id)
                                            return next
                                        })
                                        if (activePage !== id) onPageChange(id)
                                        return
                                    }

                                    setClosed((current) => {
                                        const next = new Set(current)
                                        next.delete(id)
                                        return next
                                    })
                                    onPageChange(id)
                                }}
                                title={collapsed ? label : undefined}
                                aria-current={activePage === id ? 'page' : undefined}
                                aria-expanded={children ? expanded : undefined}
                            >
                                <Icon size={19} strokeWidth={1.8} />
                                {!collapsed && <span>{label}</span>}
                                {!collapsed && children && (
                                    <ChevronDown
                                        size={15}
                                        className={`nav-item-chevron${expanded ? ' is-open' : ''}`}
                                    />
                                )}
                            </button>

                            {children && expanded && (
                                <div className="nav-submenu" role="group" aria-label={`${label} pages`}>
                                    {children.map((child) => (
                                        <button
                                            key={child.id}
                                            type="button"
                                            className={`nav-item nav-subitem ${activePage === child.id ? 'active' : ''}`}
                                            onClick={() => onPageChange(child.id)}
                                            title={collapsed ? child.label : undefined}
                                            aria-current={activePage === child.id ? 'page' : undefined}
                                        >
                                            <child.icon size={17} strokeWidth={1.8} />
                                            {!collapsed && <span>{child.label}</span>}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )
                })}
            </nav>

            <div className="sidebar-bottom">
                <button
                    type="button"
                    className={`nav-item ${activePage === 'about' ? 'active' : ''}`}
                    onClick={() => onPageChange('about')}
                    title={collapsed ? 'About' : undefined}
                    aria-current={activePage === 'about' ? 'page' : undefined}
                >
                    <Info size={19} strokeWidth={1.8} />
                    {!collapsed && <span>About</span>}
                </button>

                {!collapsed && (
                    <span className="sidebar-version">
                        VERSION {version || 'Unavailable'}
                    </span>
                )}
            </div>
        </aside>
    )
}
