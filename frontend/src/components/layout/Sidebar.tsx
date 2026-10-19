import {
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
                {navigation.map(({ id, label, icon: Icon }) => (
                    <button
                        key={id}
                        type="button"
                        className={`nav-item ${activePage === id ? 'active' : ''}`}
                        onClick={() => onPageChange(id)}
                        title={collapsed ? label : undefined}
                        aria-current={activePage === id ? 'page' : undefined}
                    >
                        <Icon size={19} strokeWidth={1.8} />
                        {!collapsed && <span>{label}</span>}
                    </button>
                ))}
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
