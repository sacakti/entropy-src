
import { useRef, useState } from 'react'
import {
    Bell,
    Check,
    CheckCheck,
    ChevronDown,
    ChevronRight,
    HelpCircle,
    LogOut,
    Moon,
    ShieldCheck,
    Sun,
    Settings,
    Trash2,
} from 'lucide-react'

import type { Profile } from '../../api/profile.api'
import Avatar from '../../features/settings/Avatar'
import type { PageId } from '../../types/navigation'
import { useDismiss } from './useDismiss'

export interface TopbarNotification {
    id: string
    title: string
    message: string
    createdAt?: string
    read: boolean
}

interface TopbarProps {
    profile: Pick<Profile, 'username' | 'full_name' | 'avatar_url'>
    onOpenHelp: () => void
    pageTitle: string
    /** Section the page belongs to, e.g. Administration for Users. */
    parentTitle?: string
    onParentClick?: () => void
    theme: 'dark' | 'light'
    onToggleTheme: () => void
    onPageChange: (page: PageId) => void
    onLogout: () => void

    notifications: TopbarNotification[]
    onMarkNotificationRead: (id: string) => void
    onClearNotification: (id: string) => void
    onMarkAllNotificationsRead: () => void
}

export default function Topbar({
    profile,
    onOpenHelp,
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
}: TopbarProps) {
    const [profileOpen, setProfileOpen] = useState(false)
    const [notificationsOpen, setNotificationsOpen] = useState(false)
    const notificationsRef = useRef<HTMLDivElement>(null)
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
                <span className="topbar-section">ENTROPY</span>
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
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon"
                    onClick={onOpenHelp}
                    aria-label="Help: keyboard shortcuts and CLI commands"
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

                                {unreadCount > 0 && (
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-link notification-mark-all"
                                        onClick={onMarkAllNotificationsRead}
                                    >
                                        <CheckCheck size={14} />
                                        Mark all read
                                    </button>
                                )}
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
                                            className={`notification-item ${
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

                                                {notification.createdAt && (
                                                    <time>
                                                        {notification.createdAt}
                                                    </time>
                                                )}
                                            </div>

                                            <div className="notification-item-actions">
                                                {!notification.read && (
                                                    <button
                                                        type="button"
                                                        title="Mark as read"
                                                        aria-label={`Mark "${notification.title}" as read`}
                                                        onClick={() =>
                                                            onMarkNotificationRead(
                                                                notification.id,
                                                            )
                                                        }
                                                    >
                                                        <Check size={15} />
                                                        <span>Read</span>
                                                    </button>
                                                )}

                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm notification-clear"
                                                    title="Clear notification"
                                                    aria-label={`Clear "${notification.title}"`}
                                                    onClick={() =>
                                                        onClearNotification(
                                                            notification.id,
                                                        )
                                                    }
                                                >
                                                    <Trash2 size={15} />
                                                    <span>Clear</span>
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
                                <Avatar profile={profile} size={40} />
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
