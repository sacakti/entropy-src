import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
    BadgeCheck,
    Blocks,
    CalendarClock,
    FolderLock,
    KeyRound,
    UserRound,
    UsersRound,
    Workflow as WorkflowIcon,
    type LucideIcon,
} from 'lucide-react'

import './EntropyShell.css'
import { getApplicationVersion } from './api/version'
import { accentTokens } from './features/preferences/accent'
import { useAppearance } from './features/preferences/useAppearance'
import WallpaperLayer from './features/preferences/WallpaperLayer'
import { WallpaperContext, useShuffledWallpaper, type WallpaperState } from './features/preferences/wallpaper'
import Topbar from './components/layout/Topbar'
import { NotificationCenterContext } from './features/notifications/context'
import { useNotifications } from './features/notifications/useNotifications'
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
import Runs from './features/runs/Runs'
import RunDetail from './features/runs/RunDetail'
import { runIdFromHash } from './features/runs/navigation'
import Nodes from './features/nodes/Nodes'
import Schedules from './features/schedules/Schedules'
import Plugins from './features/plugins/Plugins'
import Administration from './features/administration/Administration'
import AdminSystem from './features/administration/AdminSystem'
import AdminUsers from './features/administration/AdminUsers'
import AdminGroups from './features/administration/AdminGroups'
import AdminRoles from './features/administration/AdminRoles'
import AdminPermissions from './features/administration/AdminPermissions'

import { PAGE_PERMISSIONS, pageFromHash, parentPage, type PageId } from './types/navigation'
import AccessRestricted from './components/layout/AccessRestricted'
import { requestCreate, type CreateTarget } from './features/quickCreate'
import { getCurrentUser } from './services/auth'

const ShellPanel = lazy(() => import('./features/shell/ShellPanel'))

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
    const [shellOpen, setShellOpen] = useState(false)

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
        'mod+`': () => setShellOpen((open) => !open),
    })

    const [activePage, setActivePageState] = useState<PageId>(
        () => pageFromHash(window.location.hash) ?? 'dashboard',
    )
    // The run shown by the live run screen (`#/runs/<id>`).
    const [runId, setRunId] = useState<number | null>(() => runIdFromHash(window.location.hash))

    // Each page visit is a history entry, so browser Back/Forward move between pages.
    const setActivePage = useCallback((page: PageId) => {
        setActivePageState(page)
        setRunId(null)

        if (window.location.hash !== `#/${page}`) {
            window.history.pushState(null, '', `#/${page}`)
        }
    }, [])

    useEffect(() => {
        if (!pageFromHash(window.location.hash)) {
            window.history.replaceState(null, '', `#/${activePage}`)
        }

        function handlePopState() {
            setActivePageState(pageFromHash(window.location.hash) ?? 'dashboard')
            setRunId(runIdFromHash(window.location.hash))
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
        // Portaled dialogs and toasts read the glass style from <html>.
        root.dataset.glass = appearance.glass ? 'on' : 'off'
        root.style.setProperty('--app-accent', accent.accent)
        root.style.setProperty('--app-accent-text', accent.onAccent)
        root.style.setProperty('--app-accent-fg', accent.foreground)
    }, [accent, appearance.theme, appearance.glass])
    const pageTitles: Record<PageId, string> = {
        dashboard: 'Dashboard',
        plugins: 'Plugins',
        workflows: 'Workflows',
        runs: 'Runs',
        vault: 'Vault',
        nodes: 'Nodes',
        schedulers: 'Schedulers',
        administration: 'Administration',
        'admin-users': 'Users',
        'admin-groups': 'Groups',
        'admin-roles': 'Roles',
        'admin-permissions': 'Permissions',
        'admin-system': 'System',
        about: 'About',
        settings: 'Settings',
        preferences: 'Preferences',
        permissions: 'Permissions',
    }
    const pageTitle = pageTitles[activePage]

    // Effective permissions, re-read on navigation so role changes apply
    // without signing in again.
    const [permissions, setPermissions] = useState<Set<string> | null>(null)

    useEffect(() => {
        let active = true

        getCurrentUser()
            .then((result) => {
                if (active) setPermissions(new Set(result.permissions))
            })
            .catch(() => undefined)

        return () => {
            active = false
        }
    }, [activePage])

    const requiredPermissions = PAGE_PERMISSIONS[activePage]
    const restricted = Boolean(
        permissions &&
            requiredPermissions &&
            !requiredPermissions.some((permission) => permissions.has(permission)),
    )

    const quickCreate = (
        [
            { target: 'plugin', label: 'Plugin', icon: Blocks, page: 'plugins', permission: 'plugins.write' },
            { target: 'workflow', label: 'Workflow', icon: WorkflowIcon, page: 'workflows', permission: ['workflows.write', 'plugins.read'] },
            { target: 'schedule', label: 'Schedule', icon: CalendarClock, page: 'schedulers', permission: 'schedules.manage' },
            { target: 'vault-entry', label: 'Vault secret', icon: KeyRound, page: 'vault', permission: null },
            { target: 'vault-namespace', label: 'Vault namespace', icon: FolderLock, page: 'vault', permission: 'vault.namespace.create' },
            { target: 'user', label: 'User', icon: UserRound, page: 'admin-users', permission: 'users.create' },
            { target: 'group', label: 'Group', icon: UsersRound, page: 'admin-groups', permission: 'groups.create' },
            { target: 'role', label: 'Role', icon: BadgeCheck, page: 'admin-roles', permission: 'roles.create' },
        ] as {
            target: CreateTarget
            label: string
            icon: LucideIcon
            page: PageId
            permission: string | string[] | null
        }[]
    )
        .filter(
            (item) =>
                !item.permission ||
                ([] as string[]).concat(item.permission).every((permission) => permissions?.has(permission)),
        )
        .map((item) => ({
            ...item,
            onSelect: () => {
                requestCreate(item.target)
                setActivePage(item.page)
            },
        }))
    const notifications = useNotifications()
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

    return (
        <NotificationCenterContext.Provider value={notifications.push}>
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
                    onToggleShell={() => setShellOpen((open) => !open)}
                    shellOpen={shellOpen}
                    quickCreate={quickCreate}
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
                    notifications={notifications.items}
                    onMarkNotificationRead={notifications.markRead}
                    onClearNotification={notifications.remove}
                    onMarkAllNotificationsRead={notifications.markAllRead}
                    onClearAllNotifications={notifications.clear}
                />
                    <main className="entropy-content">
                        {restricted ? (
                        <AccessRestricted
                            page={pageTitle}
                            permissions={requiredPermissions ?? []}
                            onBack={window.history.length > 1 ? () => window.history.back() : undefined}
                        />
                    ) : activePage === 'dashboard' ? (
                            <Dashboard />
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
                        ) : activePage === 'runs' ? (
                            runId !== null ? (
                                <RunDetail
                                    key={runId}
                                    runId={runId}
                                    onBack={() => setActivePage('runs')}
                                />
                            ) : (
                                <Runs />
                            )
                        ) : activePage === 'nodes' ? (
                            <Nodes />
                        ) : activePage === 'schedulers' ? (
                            <Schedules />
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
                        ) : activePage === 'admin-system' ? (
                            <AdminSystem />
                        ) : null}
                    </main>
                </div>

                {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
                {shellOpen && (
                    <Suspense fallback={null}>
                        <ShellPanel username={profile.username} onClose={() => setShellOpen(false)} />
                    </Suspense>
                )}
            </div>
        </WallpaperContext.Provider>
        </NotificationCenterContext.Provider>
    )
}

export default EntropyShell
