import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ArrowUp, Check, Copy, Eye, Folder, FolderOpen, GitBranch, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { apiRequest } from '../../../services/api'
import RepositoryBrowser from './RepositoryBrowser'
import Dialog from '../../../components/layout/Dialog'
import './git-repositories.css'
import EntropyLoader from '../../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../../components/feedback/useToast'

type Assignment = { target_type: 'workflow' | 'plugin'; target_key: string }
type Repository = {
    id: number; name: string; scope: 'user' | 'project'; project_id: number | null
    created_by: string; created_at: string; assignments: Assignment[]; can_manage: boolean; clone_path: string
    source_type: 'managed' | 'local' | 'remote'; source_display: string
}
type Target = { key: string; name: string }
type RepositoryData = {
    items: Repository[]; project: { id: number; key: string; name: string }
    permissions: { project_write: boolean }
}
type Targets = { workflows: Target[]; plugins: Target[] }
type LocalDirectoryListing = {
    path: string; parent_path: string | null; is_git_repository: boolean
    directories: { name: string; path: string }[]; truncated: boolean
}

function suggestedRepositoryName(location: string) {
    const lastPart = location.trim().replace(/[\\/]+$/, '').split(/[\\/:]/).pop() ?? ''
    return lastPart.replace(/\.git$/i, '').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[.-]+|[.-]+$/g, '').slice(0, 80)
}

export default function GitRepositories() {
    const { notify, modal } = useFeedback()
    const [data, setData] = useState<RepositoryData | null>(null)
    const [targets, setTargets] = useState<Targets>({ workflows: [], plugins: [] })
    const [name, setName] = useState('')
    const [scope, setScope] = useState<'user' | 'project'>('project')
    const [sourceType, setSourceType] = useState<'managed' | 'local' | 'remote'>('managed')
    const [sourceLocation, setSourceLocation] = useState('')
    const [drafts, setDrafts] = useState<Record<number, Assignment[]>>({})
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)
    const [browsing, setBrowsing] = useState<Repository | null>(null)
    const [pathPickerOpen, setPathPickerOpen] = useState(false)
    const [pathListing, setPathListing] = useState<LocalDirectoryListing | null>(null)
    const [pathPickerError, setPathPickerError] = useState('')
    useErrorToast(pathPickerError)
    const [pathPickerLoading, setPathPickerLoading] = useState(false)

    const refresh = useCallback(async () => {
        const result = await apiRequest<RepositoryData>('/api/git-repositories')
        setData(result)
        if (!result.permissions.project_write) {
            setScope((current) => current === 'project' ? 'user' : current)
        }
        setDrafts(Object.fromEntries(result.items.map((repo) => [repo.id, repo.assignments])))
        if (result.permissions.project_write) {
            const options = await apiRequest<Targets>('/api/git-repositories/targets')
            setTargets(options)
        }
        setError('')
    }, [])

    useEffect(() => { void refresh().catch((reason: Error) => setError(reason.message)) }, [refresh])

    const loadServerDirectory = async (path: string) => {
        setPathPickerLoading(true); setPathPickerError('')
        try {
            const result = await apiRequest<LocalDirectoryListing>(`/api/git-repositories/sources/local/directories?${new URLSearchParams({ path })}`)
            setPathListing(result)
        } catch (reason) { setPathPickerError((reason as Error).message) }
        finally { setPathPickerLoading(false) }
    }

    const openPathPicker = () => {
        setPathListing(null); setPathPickerError(''); setPathPickerOpen(true)
        void loadServerDirectory(sourceLocation.trim() || '/')
    }

    const selectServerPath = () => {
        if (!pathListing?.is_git_repository) return
        setSourceLocation(pathListing.path)
        if (!name.trim()) setName(suggestedRepositoryName(pathListing.path))
        setPathPickerOpen(false)
    }

    const createRepository = async (event: FormEvent) => {
        event.preventDefault()
        if (!name.trim()) return
        setBusy(true)
        try {
            await apiRequest<Repository>('/api/git-repositories', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name.trim(), scope, source_type: sourceType,
                    source_location: sourceType === 'managed' ? null : sourceLocation.trim() }),
            })
            setName(''); setSourceLocation(''); await refresh()
            notify.success(`${scope === 'user' ? 'Personal' : 'Project'} repository ${sourceType === 'managed' ? 'created' : 'imported'}.`, { title: 'Repository ready' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to create repository' }) }
        finally { setBusy(false) }
    }

    const toggleAssignment = (repository: Repository, assignment: Assignment) => {
        setDrafts((current) => {
            const existing = current[repository.id] ?? []
            const has = existing.some((item) => item.target_type === assignment.target_type && item.target_key === assignment.target_key)
            return { ...current, [repository.id]: has
                ? existing.filter((item) => item.target_type !== assignment.target_type || item.target_key !== assignment.target_key)
                : [...existing, assignment] }
        })
    }

    const saveAssignments = async (repository: Repository) => {
        setBusy(true)
        try {
            await apiRequest(`/api/git-repositories/${repository.id}/assignments`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ assignments: drafts[repository.id] ?? [] }),
            })
            await refresh()
            notify.success(`Assignments saved for ${repository.name}.`, { title: 'Repository assignments saved' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to save assignments' }) }
        finally { setBusy(false) }
    }

    const deleteRepository = async (repository: Repository) => {
        const confirmed = await modal.confirm({
            title: 'Delete repository?',
            message: `Permanently delete ${repository.name} and its Git history? Workflows and plugins assigned to it will no longer receive a checkout.`,
            confirmText: 'Delete repository', destructive: true,
        })
        if (!confirmed) return
        try {
            await apiRequest(`/api/git-repositories/${repository.id}`, { method: 'DELETE' })
            await refresh(); notify.success(`${repository.name} deleted.`, { title: 'Repository deleted' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to delete repository' }) }
    }

    const copyClonePath = async (repository: Repository) => {
        try {
            await navigator.clipboard.writeText(`git clone '${repository.clone_path.replaceAll("'", "'\\''")}'`)
            notify.success('Clone command copied.', { title: 'Copied' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to copy clone command' }) }
    }

    const hasDraftChanges = (repository: Repository) => {
        const current = drafts[repository.id] ?? []
        return current.length !== repository.assignments.length || current.some((item) =>
            !repository.assignments.some((saved) => saved.target_type === item.target_type && saved.target_key === item.target_key),
        )
    }

    return <section className="git-repositories-tool">
        {browsing ? <RepositoryBrowser repository={browsing} onBack={() => setBrowsing(null)} /> : <>
        <header className="git-repositories-heading">
            <div><span className="git-repositories-mark"><GitBranch size={21} /></span><div><h3>Git repositories</h3><p>Create server-managed repositories and make checkouts available to workflows or plugins.</p></div></div>
            <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void refresh()} title="Refresh repositories"><RefreshCw size={15} /></button>
        </header>
        <form className="git-repository-create" onSubmit={(event) => void createRepository(event)}>
            <label>Repository name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="deployment-scripts" maxLength={80} required /></label>
            <label>Access scope<select value={scope} onChange={(event) => setScope(event.target.value as 'user' | 'project')}><option value="project" disabled={!data?.permissions.project_write}>Project — members with workflow access</option><option value="user">Personal — only you</option></select></label>
            <label>Repository source<select value={sourceType} onChange={(event) => setSourceType(event.target.value as 'managed' | 'local' | 'remote')}><option value="managed">New Entropy repository</option><option value="local">Existing server path</option><option value="remote">Remote Git repository</option></select></label>
            {sourceType !== 'managed' && <label className="git-repository-source-location">{sourceType === 'local' ? 'Git repository path on the Entropy server' : 'HTTPS or SSH clone URL'}<span className="git-repository-source-input"><input value={sourceLocation} onChange={(event) => setSourceLocation(event.target.value)} onBlur={() => { if (!name.trim()) setName(suggestedRepositoryName(sourceLocation)) }} placeholder={sourceType === 'local' ? '/srv/git/deployment-scripts' : 'git@github.com:org/repo.git'} maxLength={2048} required />{sourceType === 'local' && <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={openPathPicker}><FolderOpen size={15} /> Browse server</button>}</span></label>}
            <button type="submit" className="entropy-button entropy-button-primary" disabled={busy || !name.trim() || (sourceType !== 'managed' && !sourceLocation.trim()) || (scope === 'project' && !data?.permissions.project_write)}><Plus size={16} /> {busy ? 'Preparing…' : sourceType === 'managed' ? 'Create repository' : 'Import repository'}</button>
            <small>Personal repositories are private to your account. Project repositories can be used by members of {data?.project.name ?? 'the active project'} with workflow access. Remote URLs must not contain passwords or tokens. Private remotes use the Entropy server’s SSH key or Git credential helper.</small>
        </form>

        {!data ? <EntropyLoader label="Loading repositories…" /> : data.items.length ? <div className="git-repository-list">
            {data.items.map((repository) => <article className="git-repository-card" key={repository.id}>
                <div className="git-repository-card-heading"><span className="git-repository-mark"><GitBranch size={18} /></span><div><strong>{repository.name}</strong><span>{repository.scope === 'user' ? 'Personal · private to you' : `${data.project.name} · project scoped`} · {repository.source_display} · Created by {repository.created_by}</span></div><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setBrowsing(repository)}><Eye size={15} /> Browse</button>{repository.can_manage && <button type="button" className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm" onClick={() => void deleteRepository(repository)} title="Delete repository"><Trash2 size={16} /></button>}</div>
                <div className="git-clone-command"><code>git clone '{repository.clone_path}'</code><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => void copyClonePath(repository)} title="Copy clone command"><Copy size={15} /></button></div>
                <p className="git-repository-help">Clone this path on the Entropy server to add commits. Assigned repositories are cloned into each run workspace.</p>
                {repository.can_manage && data.permissions.project_write && <details className="git-repository-assignments">
                    <summary>Workflow and plugin assignments <span>{(drafts[repository.id] ?? []).length}</span></summary>
                    <div className="git-assignment-columns">
                        <fieldset><legend>Workflows</legend>{targets.workflows.length ? targets.workflows.map((target) => <label key={target.key}><input type="checkbox" checked={(drafts[repository.id] ?? []).some((item) => item.target_type === 'workflow' && item.target_key === target.key)} onChange={() => toggleAssignment(repository, { target_type: 'workflow', target_key: target.key })} /> {target.name}</label>) : <small>No workflows in this project.</small>}</fieldset>
                        <fieldset><legend>Plugins</legend>{targets.plugins.length ? targets.plugins.map((target) => <label key={target.key}><input type="checkbox" checked={(drafts[repository.id] ?? []).some((item) => item.target_type === 'plugin' && item.target_key === target.key)} onChange={() => toggleAssignment(repository, { target_type: 'plugin', target_key: target.key })} /> {target.name}</label>) : <small>No enabled plugins.</small>}</fieldset>
                    </div>
                    <small className="git-assignment-note">Assigned checkouts are available to plugin code as <code>self.repositories['repository-name']</code> or <code>self.context.repositories['repository-name']</code>.</small>
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={busy || !hasDraftChanges(repository)} onClick={() => void saveAssignments(repository)}><Check size={15} /> Save assignments</button>
                </details>}
                {(!repository.can_manage || !data.permissions.project_write) && <div className="git-repository-assigned">Assigned to {(repository.assignments.length && repository.assignments.map((item) => `${item.target_type}: ${item.target_key}`).join(', ')) || 'no workflows or plugins'}</div>}
            </article>)}
        </div> : <div className="git-repositories-empty"><GitBranch size={28} /><strong>No repositories yet</strong><span>Create a personal or project repository to start.</span></div>}
        </>}
        {pathPickerOpen && <Dialog title="Browse Entropy server" subtitle="Choose a Git repository directory on the Entropy host." icon={<FolderOpen size={18} />} onClose={() => setPathPickerOpen(false)} className="git-server-path-dialog" footer={<><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setPathPickerOpen(false)}>Cancel</button><button type="button" className="entropy-button entropy-button-primary" onClick={selectServerPath} disabled={!pathListing?.is_git_repository || pathPickerLoading}>Use this repository</button></>}>
            <div className="git-server-path-picker">
                <div className="git-server-path-current"><code title={pathListing?.path}>{pathListing?.path ?? 'Loading path…'}</code>{pathListing?.parent_path && <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void loadServerDirectory(pathListing.parent_path!)} disabled={pathPickerLoading}><ArrowUp size={15} /> Up</button>}</div>
                {pathListing?.is_git_repository && <div className="entropy-alert entropy-alert-success" role="status">This folder is a Git repository and can be imported.</div>}
                {pathPickerLoading ? <EntropyLoader label="Loading server folders…" /> : <div className="git-server-path-list" role="listbox" aria-label="Server folders">{pathListing?.directories.map((directory) => <button type="button" role="option" key={directory.path} onClick={() => void loadServerDirectory(directory.path)}><Folder size={16} /><span>{directory.name}</span></button>)}{!pathListing?.directories.length && !pathPickerError && <div className="git-server-path-empty">No child folders in this directory.</div>}{pathListing?.truncated && <small>Showing the first 500 folders.</small>}</div>}
            </div>
        </Dialog>}
    </section>
}
