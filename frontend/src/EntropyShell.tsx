import { useState } from 'react'

import {
    Activity,
    Blocks,
    Code2,
    KeyRound,
    Server,
    Settings,
    ShieldCheck,
    Workflow,
} from 'lucide-react'

import './EntropyShell.css'
import Sidebar from './components/layout/Sidebar'
import Topbar, { type TopbarNotification } from './components/layout/Topbar'

import { useAppearance } from './features/preferences/useAppearance'
import Preferences from './features/preferences/Preferences'

import {
    pageDescriptions,
    type PageId,
} from './types/navigation'

interface EntropyShellProps {
    username: string
    onLogout: () => void
}


function EntropyShell({ username, onLogout }: EntropyShellProps) {
    const [activePage, setActivePage] = useState<PageId>('dashboard')
    const [collapsed, setCollapsed] = useState(false)
    const appearance = useAppearance()
    const pageTitles: Record<PageId, string> = {
        dashboard: 'Dashboard',
        plugins: 'Plugins',
        workflows: 'Workflows',
        vault: 'Vault',
        nodes: 'Nodes',
        schedulers: 'Schedulers',
        administration: 'Administration',
        about: 'About',
        settings: 'Settings',
        preferences: 'Preferences',
        permissions: 'Permissions',
    }
    const pageTitle = pageTitles[activePage]
    const [notifications, setNotifications] = useState<TopbarNotification[]>([])

    function markNotificationRead(id: string) {
        setNotifications((current) =>
            current.map((notification) =>
                notification.id === id
                    ? { ...notification, read: true }
                    : notification,
            ),
        )
    }

    function clearNotification(id: string) {
        setNotifications((current) =>
            current.filter((notification) => notification.id !== id),
        )
    }

    function markAllNotificationsRead() {
        setNotifications((current) =>
            current.map((notification) => ({
                ...notification,
                read: true,
            })),
        )
    }

    return (
        <div
            className={`entropy-app theme-${appearance.theme}`}
            style={{
                '--app-accent': appearance.accentColor,
                '--app-background-image': appearance.backgroundImageId !== null
                    ? `url("/api/backgrounds/${appearance.backgroundImageId}/image")`
                    : 'none',
                // '--app-background-fit': appearance.backgroundFit === 'fill'
                //     ? '100% 100%'
                //     : appearance.backgroundFit,
                '--app-background-fit':
                    appearance.backgroundFit === 'fill' ? '100% 100%' : appearance.backgroundFit,
                '--app-background-opacity': appearance.backgroundOpacity / 100,
            } as React.CSSProperties}
        >
            <Sidebar
                activePage={activePage}
                collapsed={collapsed}
                onPageChange={setActivePage}
                onToggleCollapse={() => setCollapsed((value) => !value)}
            />
            <div className="entropy-main">
                <Topbar
                username={username}
                pageTitle={pageTitle}
                theme={appearance.theme}
                onToggleTheme={() => {
                    const nextTheme =
                        appearance.theme === 'dark' ? 'light' : 'dark'

                    void appearance.saveAppearance(
                        nextTheme,
                        appearance.accentColor,
                        appearance.backgroundImageId,
                    )
                }}
                onPageChange={setActivePage}
                onLogout={onLogout}
                notifications={notifications}
                onMarkNotificationRead={markNotificationRead}
                onClearNotification={clearNotification}
                onMarkAllNotificationsRead={markAllNotificationsRead}
            />
                <main
                    className={`entropy-content${
                        activePage === 'preferences' ? ' entropy-content-preferences' : ''
                    }`}
                >
                    {activePage === 'dashboard' ? (
                        <section className="dashboard-welcome">
                            <div className="dashboard-welcome-copy">
                                <span className="welcome-mark">
                                    <Code2 size={21} />
                                </span>
                                <p className="page-eyebrow">DEPLOYMENT WORKSPACE</p>
                                <h2>Build what matters.</h2>
                                <p>
                                    Your Entropy workspace is ready. Select a section from the
                                    sidebar to get started.
                                </p>
                            </div>
                            <div className="dashboard-welcome-art" aria-hidden="true">
                                <div className="art-ring art-ring-one" />
                                <div className="art-ring art-ring-two" />
                                <img src="/entropy-logo.svg" alt="" />
                            </div>
                        </section>
                    ) : activePage === 'about' ? (
                        <section className="content-panel about-panel">
                            <img src="/entropy-logo.svg" alt="Entropy logo" />
                            <h2>Entropy</h2>
                            <p>Deployment Management Platform</p>
                            <div className="about-version">Version not configured</div>
                        </section>
                    ) : activePage === 'preferences' ? (
                        <Preferences {...appearance} />
                    ) : (
                        <section className="content-panel placeholder-panel">
                            <span className="placeholder-icon">
                                {activePage === 'plugins' && <Blocks size={25} />}
                                {activePage === 'workflows' && <Workflow size={25} />}
                                {activePage === 'vault' && <KeyRound size={25} />}
                                {activePage === 'nodes' && <Server size={25} />}
                                {activePage === 'schedulers' && <Activity size={25} />}
                                {activePage === 'administration' && <ShieldCheck size={25} />}
                                {activePage === 'settings' && <Settings size={25} />}
                                {activePage === 'permissions' && <ShieldCheck size={25} />}
                            </span>
                            <h2>{pageTitle}</h2>
                            <p>{pageDescriptions[activePage]}</p>
                            <span className="placeholder-status">
                                PAGE SHELL READY · FUNCTIONALITY NOT IMPLEMENTED
                            </span>
                        </section>
                    )}
                </main>
            </div>
        </div>
    )
}

export default EntropyShell
