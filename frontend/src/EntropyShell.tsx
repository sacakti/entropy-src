import { useState } from 'react'
import {
  Activity,
  Blocks,
  ChevronDown,
  ChevronRight,
  Code2,
  Info,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Server,
  Settings,
  ShieldCheck,
  Sun,
  Workflow,
} from 'lucide-react'
import './EntropyShell.css'

interface EntropyShellProps {
  username: string
  onLogout: () => void
}

type PageId =
  | 'dashboard'
  | 'plugins'
  | 'workflows'
  | 'vault'
  | 'nodes'
  | 'schedulers'
  | 'administration'
  | 'about'

const navigation: { id: PageId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'plugins', label: 'Plugins', icon: Blocks },
  { id: 'workflows', label: 'Workflows', icon: Workflow },
  { id: 'vault', label: 'Vault', icon: KeyRound },
  { id: 'nodes', label: 'Nodes', icon: Server },
  { id: 'schedulers', label: 'Schedulers', icon: Activity },
  { id: 'administration', label: 'Administration', icon: ShieldCheck },
]

const pageDescriptions: Record<PageId, string> = {
  dashboard: 'Monitor activity across your deployment workspace.',
  plugins: 'Develop and manage Entropy plugins.',
  workflows: 'Create, validate, and manage deployment workflows.',
  vault: 'Manage your vaults and their configuration.',
  nodes: 'Entropy execution infrastructure.',
  schedulers: 'Manage scheduled workflow executions.',
  administration: 'Manage Entropy users and access.',
  about: 'Entropy deployment management platform.',
}

function EntropyShell({ username, onLogout }: EntropyShellProps) {
  const [activePage, setActivePage] = useState<PageId>('dashboard')
  const [collapsed, setCollapsed] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  const activeItem = navigation.find((item) => item.id === activePage)
  const pageTitle = activeItem?.label ?? 'About'

  return (
    <div className={`entropy-app theme-${theme}`}>
      <aside className={`entropy-sidebar ${collapsed ? 'collapsed' : ''}`}>
        <div className="entropy-sidebar-brand">
          <img src="/entropy-logo.svg" alt="Entropy" />
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
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>

        <div className="sidebar-section-label">
          {!collapsed && 'WORKSPACE'}
        </div>

        <nav className="entropy-navigation" aria-label="Main navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={`nav-item ${activePage === id ? 'active' : ''}`}
              onClick={() => setActivePage(id)}
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
            onClick={() => setActivePage('about')}
            title={collapsed ? 'About' : undefined}
          >
            <Info size={19} strokeWidth={1.8} />
            {!collapsed && <span>About</span>}
          </button>
          {!collapsed && (
            <span className="sidebar-version">VERSION — NOT CONFIGURED</span>
          )}
        </div>
      </aside>

      <div className="entropy-main">
        <header className="entropy-topbar">
          <div className="topbar-context">
            <span className="topbar-section">ENTROPY</span>
            <ChevronRight size={14} />
            <span className="topbar-current">{pageTitle}</span>
          </div>

          <div className="topbar-actions">
            <button
              type="button"
              className="icon-button theme-toggle"
              onClick={() =>
                setTheme((value) => (value === 'dark' ? 'light' : 'dark'))
              }
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <div className="profile-container">
              <button
                type="button"
                className="profile-trigger"
                onClick={() => setProfileOpen((value) => !value)}
                aria-expanded={profileOpen}
              >
                <span className="profile-avatar">
                  {username.charAt(0).toUpperCase()}
                </span>
                <span className="profile-name">{username}</span>
                <ChevronDown size={15} />
              </button>

              {profileOpen && (
                <div className="profile-menu">
                  <div className="profile-menu-heading">
                    <span className="profile-menu-label">SIGNED IN AS</span>
                    <strong>{username}</strong>
                  </div>
                  <div className="profile-menu-divider" />
                  <button
                    type="button"
                    onClick={() => {
                      setProfileOpen(false)
                      window.alert('Settings page is not implemented yet.')
                    }}
                  >
                    <Settings size={16} />
                    Settings
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setProfileOpen(false)
                      window.alert('Permissions page is not implemented yet.')
                    }}
                  >
                    <ShieldCheck size={16} />
                    Permissions
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setProfileOpen(false)
                      setTheme((value) => (value === 'dark' ? 'light' : 'dark'))
                    }}
                  >
                    {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                    Switch theme
                  </button>
                  <div className="profile-menu-divider" />
                  <button className="profile-logout" type="button" onClick={onLogout}>
                    <LogOut size={16} />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="entropy-content">
          <div className="page-heading">
            <div>
              <p className="page-eyebrow">WORKSPACE</p>
              <h1>{pageTitle}</h1>
              <p className="page-description">{pageDescriptions[activePage]}</p>
            </div>
          </div>

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
          ) : (
            <section className="content-panel placeholder-panel">
              <span className="placeholder-icon">
                {activePage === 'plugins' && <Blocks size={25} />}
                {activePage === 'workflows' && <Workflow size={25} />}
                {activePage === 'vault' && <KeyRound size={25} />}
                {activePage === 'nodes' && <Server size={25} />}
                {activePage === 'schedulers' && <Activity size={25} />}
                {activePage === 'administration' && <ShieldCheck size={25} />}
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

