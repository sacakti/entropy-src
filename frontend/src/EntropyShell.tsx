import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
    Activity,
    Server,
} from 'lucide-react'

import './EntropyShell.css'
import { getApplicationVersion } from './api/version'
import { accentTokens } from './features/preferences/accent'
import { useAppearance } from './features/preferences/useAppearance'
import WallpaperLayer from './features/preferences/WallpaperLayer'
import { WallpaperContext, useShuffledWallpaper, type WallpaperState } from './features/preferences/wallpaper'
import Topbar, { type TopbarNotification } from './components/layout/Topbar'
import Sidebar from './components/layout/Sidebar'
import EntropyLogo from './components/layout/EntropyLogo'
import Settings from './features/settings/Settings'
import HelpDialog from './features/help/HelpDialog'
import { useFeedback } from './components/feedback/FeedbackProvider'
import { isTyping, useShortcuts } from './components/layout/useShortcuts'
import { getProfile, type Profile } from './api/profile.api'
import type { AuthUser } from './services/auth'
import Dashboard from './features/dashboard/Dashboard'
import Preferences from './features/preferences/Preferences'
import Permissions from './features/permissions/Permissions'
import Vault from './features/vault/Vault'
import Workflows from './features/workflows/Workflows'
import Plugins from './features/plugins/Plugins'
import Administration from './features/administration/Administration'
import AdminUsers from './features/administration/AdminUsers'
import AdminGroups from './features/administration/AdminGroups'
import AdminRoles from './features/administration/AdminRoles'
import AdminPermissions from './features/administration/AdminPermissions'

import { pageFromHash, parentPage, type PageId } from './types/navigation'

interface EntropyShellProps {
    user: AuthUser
    /** Display name to greet, right after signing in. */
    welcome: string | null
    onLogout: () => void
}


function EntropyShell({ user, welcome, onLogout }: EntropyShellProps) {
    const { notify } = useFeedback()
    const [profile, setProfile] = useState<Profile>(() => ({
        id: user.id,
        username: user.username,
        full_name: user.full_name,
        email: user.email,
        avatar_url: user.avatar_url ?? null,
    }))
    const [helpOpen, setHelpOpen] = useState(false)

    useEffect(() => {
        let active = true

        getProfile()
            .then((loaded) => {
                if (active) setProfile(loaded)
            })
            .catch(() => {
                // Older servers lack /api/profile; keep the session's identity.
            })

        return () => {
            active = false
        }
    }, [])

    // Greet once per sign-in (effects run twice in development).
    const greeted = useRef(false)

    useEffect(() => {
        if (!welcome || greeted.current) return
        greeted.current = true
        notify.success(`Signed in as ${welcome}.`)
    }, [notify, welcome])

    useShortcuts({
        'shift+?': (event) => {
            if (isTyping(event)) return false
            setHelpOpen(true)
        },
    })

    const [activePage, setActivePageState] = useState<PageId>(
        () => pageFromHash(window.location.hash) ?? 'dashboard',
    )

    // Each page visit is a history entry, so browser Back/Forward move between pages.
    const setActivePage = useCallback((page: PageId) => {
        setActivePageState(page)

        if (pageFromHash(window.location.hash) !== page) {
            window.history.pushState(null, '', `#/${page}`)
        }
    }, [])

    useEffect(() => {
        if (!pageFromHash(window.location.hash)) {
            window.history.replaceState(null, '', `#/${activePage}`)
        }

        function handlePopState() {
            setActivePageState(pageFromHash(window.location.hash) ?? 'dashboard')
        }

        window.addEventListener('popstate', handlePopState)
        return () => window.removeEventListener('popstate', handlePopState)
        // Only the initial page needs normalising.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
    const [collapsed, setCollapsed] = useState(false)
    const appearance = useAppearance()
    const accent = useMemo(
        () => accentTokens(appearance.accentColor, appearance.theme),
        [appearance.accentColor, appearance.theme],
    )

    const wallpaperId = useShuffledWallpaper(
        appearance.backgrounds,
        appearance.backgroundImageId,
        appearance.wallpaperSettings.shuffle,
    )
    const wallpaper = useMemo<WallpaperState>(() => {
        const background =
            appearance.backgrounds.find((item) => item.id === wallpaperId) ?? null

        return {
            background,
            fit: appearance.backgroundFit,
            opacity: appearance.backgroundOpacity / 100,
            placement: background
                ? appearance.wallpaperSettings.placements[String(background.id)]
                : undefined,
        }
    }, [
        appearance.backgrounds,
        appearance.backgroundFit,
        appearance.backgroundOpacity,
        appearance.wallpaperSettings.placements,
        wallpaperId,
    ])

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
        'admin-users': 'Users',
        'admin-groups': 'Groups',
        'admin-roles': 'Roles',
        'admin-permissions': 'Permissions',
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
        <WallpaperContext.Provider value={wallpaper}>
            <div
                className={`entropy-app theme-${appearance.theme}`}
                style={{
                    '--app-accent': accent.accent,
                    '--app-accent-text': accent.onAccent,
                    '--app-accent-fg': accent.foreground,
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
                    <WallpaperLayer />
                    <Topbar
                    profile={profile}
                    onOpenHelp={() => setHelpOpen(true)}
                    pageTitle={pageTitle}
                    parentTitle={parentPage(activePage)?.label}
                    onParentClick={() => {
                        const parent = parentPage(activePage)
                        if (parent) setActivePage(parent.id)
                    }}
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
                                <EntropyLogo size={72} />
                                <h2>Entropy</h2>
                                <p>Deployment Management Platform</p>
                                <div className="about-version">
                                    Version {appVersion || 'Unavailable'}
                                </div>
                            </section>
                        ) : activePage === 'preferences' ? (
                            <Preferences {...appearance} />
                        ) : activePage === 'settings' ? (
                            <Settings profile={profile} onProfileChange={setProfile} />
                        ) : activePage === 'permissions' ? (
                            <Permissions />
                        ) : activePage === 'vault' ? (
                            <Vault />
                        ) : activePage === 'workflows' ? (
                            <Workflows />
                        ) : activePage === 'plugins' ? (
                            <Plugins />
                        ) : activePage === 'administration' ? (
                            <Administration onNavigate={setActivePage} />
                        ) : activePage === 'admin-users' ? (
                            <AdminUsers />
                        ) : activePage === 'admin-groups' ? (
                            <AdminGroups />
                        ) : activePage === 'admin-roles' ? (
                            <AdminRoles />
                        ) : activePage === 'admin-permissions' ? (
                            <AdminPermissions />
                        ) : (
                        <section className="content-panel placeholder-panel">
                                <span className="placeholder-icon">
                                    {/* {activePage === 'plugins' && <Blocks size={25} />} */}
                                    {/* {activePage === 'workflows' && <Workflow size={25} />} */}
                                    {/* {activePage === 'vault' && <KeyRound size={25} />} */}
                                    {activePage === 'nodes' && <Server size={25} />}
                                    {activePage === 'schedulers' && <Activity size={25} />}
                                    {/* {activePage === 'settings' && <Settings size={25} />}
                                    {activePage === 'permissions' && <ShieldCheck size={25} />} */}
                                </span>
                                <span className="placeholder-status">
                                    PAGE SHELL READY · FUNCTIONALITY NOT IMPLEMENTED
                                </span>
                            </section>
                        )}
                    </main>
                </div>

                {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
            </div>
        </WallpaperContext.Provider>
    )
}

export default EntropyShell
