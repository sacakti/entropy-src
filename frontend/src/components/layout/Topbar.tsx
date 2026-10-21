
import { useRef, useState } from 'react'
import {
    Bell,
    Check,
    CheckCheck,
    ChevronDown,
    ChevronRight,
    HelpCircle,
    LogOut,
    Plus,
    Moon,
    ShieldCheck,
    Sun,
    Settings,
    SquareTerminal,
    Trash2,
    type LucideIcon,
} from 'lucide-react'

import type { AppNotification } from '../../api/notifications.api'
import type { Profile } from '../../api/profile.api'
import { openRun } from '../../features/runs/navigation'
import Avatar from '../../features/settings/Avatar'
import type { PageId } from '../../types/navigation'
import FloatingMenu from './FloatingMenu'
import ProjectSwitcher from './ProjectSwitcher'
import { useDismiss } from './useDismiss'

export type TopbarNotification = AppNotification

/** "just now", "5 min ago", "3 h ago", then a date. */
function relativeTime(value: string): string {
    const time = new Date(value).getTime()

    if (Number.isNaN(time)) return ''

    const minutes = Math.round((Date.now() - time) / 60_000)

    if (minutes < 1) return 'just now'
    if (minutes < 60) return `${minutes} min ago`
    if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`

    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(time)
}

interface TopbarProps {
    profile: Pick<Profile, 'username' | 'full_name' | 'avatar_url'>
    onOpenHelp: () => void
    /** Open or close the shell (ent commands in the browser). */
    onToggleShell: () => void
    shellOpen: boolean
    /** Open project administration; omitted when the user may not manage projects. */
    onManageProjects?: () => void
    /** Entries of the "+" menu, already filtered by permission. */
    quickCreate: { target: string; label: string; icon: LucideIcon; onSelect: () => void }[]
    pageTitle: string
    /** Section the page belongs to, e.g. Administration for Users. */
    parentTitle?: string
    onParentClick?: () => void
    theme: 'dark' | 'light'
    onToggleTheme: () => void
    onPageChange: (page: PageId) => void
    onLogout: () => void

    notifications: TopbarNotification[]
    onMarkNotificationRead: (id: number) => void
    onClearNotification: (id: number) => void
    onMarkAllNotificationsRead: () => void
    onClearAllNotifications: () => void
}

export default function Topbar({
    profile,
    onOpenHelp,
    onToggleShell,
    shellOpen,
    onManageProjects,
    quickCreate,
    pageTitle,
    parentTitle,
    onParentClick,
    theme,
    onToggleTheme,
    onPageChange,
    onLogout,
    notifications,
    onMarkNotificationRead,
    onClearNotification,
    onMarkAllNotificationsRead,
    onClearAllNotifications,
}: TopbarProps) {
    const [profileOpen, setProfileOpen] = useState(false)
    const [notificationsOpen, setNotificationsOpen] = useState(false)
    const notificationsRef = useRef<HTMLDivElement>(null)
    const createRef = useRef<HTMLButtonElement>(null)
    const [createOpen, setCreateOpen] = useState(false)
    const profileRef = useRef<HTMLDivElement>(null)
    const displayName = profile.full_name?.trim() || profile.username

    // Menus close on any press outside them, or on Escape.
    useDismiss(notificationsOpen, [notificationsRef], () => setNotificationsOpen(false))
    useDismiss(profileOpen, [profileRef], () => setProfileOpen(false))

    const unreadCount = notifications.filter(
        (notification) => !notification.read,
    ).length

    function navigateTo(page: PageId) {
        setProfileOpen(false)
        setNotificationsOpen(false)
        onPageChange(page)
    }

    return (
        <header className="entropy-topbar">
            <div className="topbar-context">
                <ProjectSwitcher onManage={onManageProjects} />
                <ChevronRight size={14} />
                {parentTitle && (
                    <>
                        <button type="button" className="topbar-parent" onClick={onParentClick}>
                            {parentTitle}
                        </button>
                        <ChevronRight size={14} />
                    </>
                )}
                <span className="topbar-current">{pageTitle}</span>
            </div>

            <div className="topbar-actions">
                {quickCreate.length > 0 && (
                    <>
                        <button
                            ref={createRef}
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon"
                            onClick={() => setCreateOpen((open) => !open)}
                            aria-label="Create new…"
                            data-tour="create"
                            aria-haspopup="menu"
                            aria-expanded={createOpen}
                            title="Create new…"
                        >
                            <Plus size={19} />
                        </button>
                        <FloatingMenu
                            anchorRef={createRef}
                            open={createOpen}
                            onClose={() => setCreateOpen(false)}
                            className="topbar-create-menu"
                        >
                            <span className="topbar-create-label">Create new</span>
                            {quickCreate.map((item) => (
                                <button
                                    key={item.target}
                                    type="button"
                                    role="menuitem"
                                    onClick={() => {
                                        setCreateOpen(false)
                                        item.onSelect()
                                    }}
                                >
                                    <item.icon size={15} aria-hidden="true" />
                                    {item.label}
                                </button>
                            ))}
                        </FloatingMenu>
                    </>
                )}

                <button
                    type="button"
                    className={`entropy-button entropy-button-ghost entropy-button-icon${shellOpen ? ' is-active' : ''}`}
                    onClick={onToggleShell}
                    aria-label="Shell: run ent commands"
                    data-tour="shell"
                    aria-pressed={shellOpen}
                    title="Shell (Ctrl+`)"
                >
                    <SquareTerminal size={18} />
                </button>

                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon"
                    onClick={onOpenHelp}
                    aria-label="Help: keyboard shortcuts and CLI commands"
                    data-tour="help"
                    title="Help (?)"
                >
                    <HelpCircle size={18} />
                </button>

                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon theme-toggle"
                    onClick={onToggleTheme}
                    aria-label={`Switch to ${
                        theme === 'dark' ? 'light' : 'dark'
                    } theme`}
                    title={`Switch to ${
                        theme === 'dark' ? 'light' : 'dark'
                    } theme`}
                >
                    {theme === 'dark'
                        ? <Sun size={18} />
                        : <Moon size={18} />}
                </button>

                <div className="notification-container" ref={notificationsRef}>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon notification-trigger"
                        data-tour="notifications"
                        onClick={() => {
                            setNotificationsOpen((open) => !open)
                            setProfileOpen(false)
                        }}
                        aria-label={
                            unreadCount > 0
                                ? `Notifications, ${unreadCount} unread`
                                : 'Notifications'
                        }
                        aria-expanded={notificationsOpen}
                        aria-haspopup="true"
                        title="Notifications"
                    >
                        <Bell size={18} />
                        {unreadCount > 0 && (
                            <span className="notification-badge">
                                {unreadCount > 99 ? '99+' : unreadCount}
                            </span>
                        )}
                    </button>

                    {notificationsOpen && (
                        <div
                            className="notification-menu"
                            role="region"
                            aria-label="Notification center"
                        >
                            <div className="notification-menu-heading">
                                <div>
                                    <strong>Notifications</strong>
                                    <span>
                                        {unreadCount > 0
                                            ? `${unreadCount} unread`
                                            : 'All caught up'}
                                    </span>
                                </div>

                                <div className="notification-menu-actions">
                                    {unreadCount > 0 && (
                                        <button
                                            type="button"
                                            className="notif-action"
                                            onClick={onMarkAllNotificationsRead}
                                        >
                                            <CheckCheck size={14} />
                                            Mark all read
                                        </button>
                                    )}
                                    {notifications.length > 0 && (
                                        <button
                                            type="button"
                                            className="notif-action is-danger"
                                            onClick={onClearAllNotifications}
                                        >
                                            <Trash2 size={14} />
                                            Clear all
                                        </button>
                                    )}
                                </div>
                            </div>

                            <div className="notification-menu-divider" />

                            {notifications.length === 0 ? (
                                <div className="notification-empty">
                                    <Bell size={23} />
                                    <strong>No new messages</strong>
                                    <span>
                                        You're all caught up.
                                    </span>
                                </div>
                            ) : (
                                <div className="notification-list">
                                    {notifications.map((notification) => (
                                        <article
                                            key={notification.id}
                                            className={`notification-item is-${notification.level} ${
                                                notification.read
                                                    ? 'is-read'
                                                    : 'is-unread'
                                            }`}
                                        >
                                            <div className="notification-item-content">
                                                <div className="notification-item-title">
                                                    {!notification.read && (
                                                        <span
                                                            className="notification-unread-dot"
                                                            aria-label="Unread"
                                                        />
                                                    )}
                                                    <strong>
                                                        {notification.title}
                                                    </strong>
                                                </div>

                                                <p>{notification.message}</p>

                                                {notification.source?.startsWith('run:') && (
                                                    <button
                                                        type="button"
                                                        className="notification-link"
                                                        onClick={() => {
                                                            setNotificationsOpen(false)
                                                            if (!notification.read) onMarkNotificationRead(notification.id)
                                                            openRun(Number(notification.source?.slice(4)))
                                                        }}
                                                    >
                                                        Open run
                                                    </button>
                                                )}

                                                <time dateTime={notification.created_at}>
                                                    {relativeTime(notification.created_at)}
                                                </time>
                                            </div>

                                            <div className="notification-item-actions">
                                                {!notification.read && (
                                                    <button
                                                        type="button"
                                                        className="notif-icon-action"
                                                        title="Mark as read"
                                                        aria-label={`Mark "${notification.title}" as read`}
                                                        onClick={() =>
                                                            onMarkNotificationRead(
                                                                notification.id,
                                                            )
                                                        }
                                                    >
                                                        <Check size={15} />
                                                    </button>
                                                )}

                                                <button
                                                    type="button"
                                                    className="notif-icon-action is-danger"
                                                    title="Clear notification"
                                                    aria-label={`Clear "${notification.title}"`}
                                                    onClick={() =>
                                                        onClearNotification(
                                                            notification.id,
                                                        )
                                                    }
                                                >
                                                    <Trash2 size={15} />
                                                </button>
                                            </div>
                                        </article>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className="profile-container" ref={profileRef}>
                    <button
                        type="button"
                        className="profile-trigger"
                        data-tour="profile"
                        onClick={() => {
                            setProfileOpen((open) => !open)
                            setNotificationsOpen(false)
                        }}
                        aria-expanded={profileOpen}
                        aria-haspopup="true"
                    >
                        <Avatar profile={profile} size={30} className="profile-avatar" />

                        <span className="profile-name" title={displayName}>
                            {displayName}
                        </span>
                        <ChevronDown size={15} />
                    </button>

                    {profileOpen && (
                        <div className="profile-menu">
                            <div className="profile-menu-heading">
                                <Avatar profile={profile} size={40} zoomable />
                                <div>
                                    <span className="profile-menu-label">
                                        SIGNED IN AS
                                    </span>
                                    <strong>{displayName}</strong>
                                    <small>@{profile.username}</small>
                                </div>
                            </div>

                            <div className="profile-menu-divider" />

                            <button
                                type="button"
                                onClick={() => navigateTo('settings')}
                            >
                                <Settings size={16} />
                                Settings
                            </button>

                            <button
                                type="button"
                                onClick={() => navigateTo('preferences')}
                            >
                                <Sun size={16} />
                                Preferences
                            </button>

                            <button
                                type="button"
                                onClick={() => navigateTo('permissions')}
                            >
                                <ShieldCheck size={16} />
                                Permissions
                            </button>

                            <div className="profile-menu-divider" />

                            <button
                                className="profile-logout"
                                type="button"
                                onClick={() => {
                                    setProfileOpen(false)
                                    onLogout()
                                }}
                            >
                                <LogOut size={16} />
                                Sign out
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </header>
    )
}
