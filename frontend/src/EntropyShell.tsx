import { useEffect, useMemo, useState } from 'react'

import {
    Activity,
    Server,
    ShieldCheck,
} from 'lucide-react'

import './EntropyShell.css'
import { getApplicationVersion } from './api/version'
import { accentTokens } from './features/preferences/accent'
import { useAppearance } from './features/preferences/useAppearance'
import Topbar, { type TopbarNotification } from './components/layout/Topbar'
import Sidebar from './components/layout/Sidebar'
import ChangePasswordForm from './features/settings/ChangePasswordForm'
import Dashboard from './features/dashboard/Dashboard'
import Preferences from './features/preferences/Preferences'
import Permissions from './features/permissions/Permissions'
import Vault from './features/vault/Vault'
import Workflows from './features/workflows/Workflows'
import Plugins from './features/plugins/Plugins'

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
    const accent = useMemo(
        () => accentTokens(appearance.accentColor, appearance.theme),
        [appearance.accentColor, appearance.theme],
    )

    // Mirror the theme on <html> for dialogs and toasts rendered outside .entropy-app.
    useEffect(() => {
        const root = document.documentElement

        root.dataset.theme = appearance.theme
        root.style.setProperty('--app-accent', accent.accent)
        root.style.setProperty('--app-accent-text', accent.onAccent)
        root.style.setProperty('--app-accent-fg', accent.foreground)
    }, [accent, appearance.theme])
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
    const [appVersion, setAppVersion] = useState('')

    useEffect(() => {
        let active = true

        getApplicationVersion()
            .then((data) => {
                if (active) {
                    setAppVersion(data.version)
                }
            })
            .catch(() => {
                if (active) {
                    setAppVersion('')
                }
            })

        return () => {
            active = false
        }
    }, [])

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
                '--app-accent': accent.accent,
                '--app-accent-text': accent.onAccent,
                '--app-accent-fg': accent.foreground,
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
                version={appVersion}
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
                <main className="entropy-content">
                    {activePage === 'dashboard' ? (
                        <Dashboard
                            onNavigate={setActivePage}
                        />
                    ) : activePage === 'about' ? (
                        <section className="content-panel about-panel">
                            <img src="/entropy-logo.svg" alt="Entropy logo" />
                            <h2>Entropy</h2>
                            <p>Deployment Management Platform</p>
                            <div className="about-version">
                                Version {appVersion || 'Unavailable'}
                            </div>
                        </section>
                    ) : activePage === 'preferences' ? (
                        <Preferences {...appearance} />
                    ) : activePage === 'settings' ? (
                            <ChangePasswordForm />
                    ) : activePage === 'permissions' ? (
                        <Permissions />
                    ) : activePage === 'vault' ? (
                        <Vault />
                    ) : activePage === 'workflows' ? (
                    <Workflows />
                ) : activePage === 'plugins' ? (
                    <Plugins />
                ) : (
                    <section className="content-panel placeholder-panel">
                            <span className="placeholder-icon">
                                {/* {activePage === 'plugins' && <Blocks size={25} />} */}
                                {/* {activePage === 'workflows' && <Workflow size={25} />} */}
                                {/* {activePage === 'vault' && <KeyRound size={25} />} */}
                                {activePage === 'nodes' && <Server size={25} />}
                                {activePage === 'schedulers' && <Activity size={25} />}
                                {activePage === 'administration' && <ShieldCheck size={25} />}
                                {/* {activePage === 'settings' && <Settings size={25} />}
                                {activePage === 'permissions' && <ShieldCheck size={25} />} */}
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
