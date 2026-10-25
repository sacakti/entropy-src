import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react'
import Editor from '@monaco-editor/react'
import { ArrowLeft, ChevronDown, FileCode2, FilePlus2, FolderUp, GitBranch, GitCommitHorizontal, LoaderCircle, Plus, Save, Upload } from 'lucide-react'
import { apiRequest } from '../../../services/api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import Dialog from '../../../components/layout/Dialog'
import DiffView from '../../plugins/editor/DiffView'
import '../../plugins/editor/monaco'

type Branches = { branches: string[]; committed_branches: string[]; default_branch: string | null }
type Commit = { sha: string; short_sha: string; subject: string; author: string; date: string }
type CommitChange = { path: string; status: string; original: string; modified: string; binary: boolean }
type RepoFile = { path: string; created_at: string; created_by: string; modified_at: string; modified_by: string; size: number }
type FileData = { path: string; content: string; binary: boolean; size: number }
type View = 'files' | 'editor'

function query(params: Record<string, string>) { return new URLSearchParams(params).toString() }
function languageOf(path: string) {
    const extension = path.split('.').pop()?.toLowerCase()
    const languages: Record<string, string> = { py: 'python', json: 'json', yml: 'yaml', yaml: 'yaml', md: 'markdown' }
    return languages[extension ?? ''] ?? 'plaintext'
}
function formatDate(value: string) {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function RepositoryBrowser({ repository, onBack }: {
    repository: { id: number; name: string; clone_path: string; can_manage: boolean; source_display: string }
    onBack: () => void
}) {
    const { notify } = useFeedback()
    const [branches, setBranches] = useState<string[]>([])
    const [committedBranches, setCommittedBranches] = useState<string[]>([])
    const [branch, setBranch] = useState('main')
    const [branchDraft, setBranchDraft] = useState('main')
    const [branchPickerOpen, setBranchPickerOpen] = useState(false)
    const [branchCreateOpen, setBranchCreateOpen] = useState(false)
    const [branchCreateName, setBranchCreateName] = useState('')
    const [baseBranch, setBaseBranch] = useState('')
    const [branchError, setBranchError] = useState('')
    const [files, setFiles] = useState<RepoFile[]>([])
    const [commits, setCommits] = useState<Commit[]>([])
    const [commitChanges, setCommitChanges] = useState<CommitChange[]>([])
    const [selectedChange, setSelectedChange] = useState<CommitChange | null>(null)
    const [sideBySide, setSideBySide] = useState(true)
    const [selectedFile, setSelectedFile] = useState<FileData | null>(null)
    const [content, setContent] = useState('')
    const [view, setView] = useState<View>('files')
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState('')
    const [dragging, setDragging] = useState(false)
    const [uploadMenuOpen, setUploadMenuOpen] = useState(false)
    const [createDialogOpen, setCreateDialogOpen] = useState(false)
    const [newFilePath, setNewFilePath] = useState('')
    const [newFileError, setNewFileError] = useState('')
    const [isNewFile, setIsNewFile] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)
    const folderInputRef = useRef<HTMLInputElement>(null)
    const theme = useMemo(() => document.querySelector('.entropy-app')?.classList.contains('theme-light') ? 'entropy-light' : 'entropy-dark', [])
    const dirty = selectedFile !== null && (isNewFile || content !== selectedFile.content)

    const loadBranch = useCallback(async (selectedBranch: string) => {
        setLoading(true); setError(''); setSelectedFile(null); setContent(''); setCommitChanges([]); setSelectedChange(null); setIsNewFile(false)
        try {
            const [fileResult, commitResult] = await Promise.all([
                apiRequest<{ files: RepoFile[] }>(`/api/git-repositories/${repository.id}/browser/files?${query({ branch: selectedBranch })}`),
                apiRequest<{ commits: Commit[] }>(`/api/git-repositories/${repository.id}/browser/commits?${query({ branch: selectedBranch })}`),
            ])
            setFiles(fileResult.files); setCommits(commitResult.commits)
        } catch (reason) { setError((reason as Error).message) }
        finally { setLoading(false) }
    }, [repository.id])

    useEffect(() => {
        let active = true
        void apiRequest<Branches>(`/api/git-repositories/${repository.id}/browser/branches`).then((result) => {
            if (!active) return
            setBranches(result.branches)
            setCommittedBranches(result.committed_branches ?? result.branches)
            setBranch(result.default_branch ?? 'main')
            setBranchDraft(result.default_branch ?? 'main')
        }).catch((reason: Error) => { if (active) { setError(reason.message); setLoading(false) } })
        return () => { active = false }
    }, [repository.id])
    useEffect(() => { setBranchDraft(branch) }, [branch])
    useEffect(() => { if (branch) void loadBranch(branch) }, [branch, loadBranch])

    const openFile = async (path: string) => {
        setLoading(true); setError(''); setCommitChanges([]); setSelectedChange(null)
        try {
            const file = await apiRequest<FileData>(`/api/git-repositories/${repository.id}/browser/file?${query({ branch, path })}`)
            setSelectedFile(file); setContent(file.content); setIsNewFile(false); setView(file.binary ? 'files' : 'editor')
        } catch (reason) { setError((reason as Error).message) }
        finally { setLoading(false) }
    }

    const openDiff = async (commit: Commit) => {
        setLoading(true); setError(''); setSelectedFile(null); setView('files'); setCommitChanges([]); setSelectedChange(null)
        try {
            const result = await apiRequest<{ changes: CommitChange[] }>(`/api/git-repositories/${repository.id}/browser/commits/${commit.sha}/diff`)
            setCommitChanges(result.changes)
            setSelectedChange(result.changes[0] ?? null)
        } catch (reason) { setError((reason as Error).message) }
        finally { setLoading(false) }
    }

    const createBranch = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        setSaving(true); setBranchError('')
        try {
            const result = await apiRequest<{ branch: string; base_branch: string }>(`/api/git-repositories/${repository.id}/browser/branches`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ branch: branchCreateName, base_branch: baseBranch }),
            })
            setBranches((current) => current.includes(result.branch) ? current : [...current, result.branch].sort())
            setCommittedBranches((current) => current.includes(result.branch) ? current : [...current, result.branch].sort())
            setBranch(result.branch); setBranchDraft(result.branch); setBranchCreateOpen(false)
            await loadBranch(result.branch)
            notify.success(`Branch ${result.branch} created from ${result.base_branch}.`, { title: 'Branch created' })
        } catch (reason) { setBranchError((reason as Error).message) }
        finally { setSaving(false) }
    }

    const chooseBranch = (name: string) => {
        setBranch(name); setBranchDraft(name); setBranchPickerOpen(false)
    }

    const uploadFiles = async (selected: FileList | File[]) => {
        const list = Array.from(selected)
        if (!list.length) return
        setSaving(true); setError('')
        try {
            for (const file of list) {
                const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
                const form = new FormData()
                form.set('branch', branch); form.set('path', path); form.set('file', file)
                await apiRequest(`/api/git-repositories/${repository.id}/browser/files`, { method: 'POST', body: form })
            }
            setCommittedBranches((current) => current.includes(branch) ? current : [...current, branch].sort())
            await loadBranch(branch)
            notify.success(`${list.length} file${list.length === 1 ? '' : 's'} added to ${branch}.`, { title: 'Files added' })
        } catch (reason) { setError((reason as Error).message); notify.error((reason as Error).message, { title: 'Unable to add files' }) }
        finally {
            setSaving(false)
            if (inputRef.current) inputRef.current.value = ''
            if (folderInputRef.current) folderInputRef.current.value = ''
        }
    }

    const saveFile = async () => {
        if (!selectedFile || !dirty) return
        const savedPath = selectedFile.path
        setSaving(true); setError('')
        try {
            await apiRequest(`/api/git-repositories/${repository.id}/browser/file`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ branch, path: selectedFile.path, content }),
            })
            setCommittedBranches((current) => current.includes(branch) ? current : [...current, branch].sort())
            await loadBranch(branch)
            await openFile(savedPath)
            notify.success(`${savedPath} saved as a new commit.`, { title: 'File saved' })
        } catch (reason) { setError((reason as Error).message); notify.error((reason as Error).message, { title: 'Unable to save file' }) }
        finally { setSaving(false) }
    }

    const createNewFile = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        const path = newFilePath.trim()
        if (!path || path.startsWith('/') || path.split('/').some((part) => !part || part === '.' || part === '..') || path.includes('\\')) {
            setNewFileError('Enter a valid relative file path, such as src/config.json.')
            return
        }
        if (files.some((file) => file.path === path)) {
            setNewFileError('A file with that path already exists. Select it from the file list to edit it.')
            return
        }
        setNewFileError('')
        setSelectedFile({ path, content: '', binary: false, size: 0 })
        setContent('')
        setIsNewFile(true)
        setView('editor')
        setCreateDialogOpen(false)
        setNewFilePath('')
    }

    const handleDrop = (event: DragEvent<HTMLDivElement>) => {
        event.preventDefault(); setDragging(false)
        if (repository.can_manage) void uploadFiles(event.dataTransfer.files)
    }

    return <section className="git-browser-page">
        <header className="git-browser-page-heading">
            <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={onBack}><ArrowLeft size={15} /> Repositories</button>
            <div><span className="git-repositories-mark"><GitBranch size={18} /></span><div><strong>{repository.name}</strong><small>{repository.source_display} · {repository.clone_path}</small></div></div>
        </header>
        <div className="git-browser-toolbar">
            <div className="git-browser-branch-picker">
                <label htmlFor="git-browser-branch-input"><GitBranch size={15} /> Branch</label>
                <div className="git-browser-branch-input-wrap"><input id="git-browser-branch-input" role="combobox" aria-expanded={branchPickerOpen} aria-controls="git-browser-branch-options" value={branchDraft} onFocus={() => setBranchPickerOpen(true)} onChange={(event) => { setBranchDraft(event.target.value); setBranchPickerOpen(true) }} onKeyDown={(event) => { if (event.key === 'Escape') setBranchPickerOpen(false); if (event.key === 'Enter') { event.preventDefault(); const match = branches.find((name) => name.toLowerCase() === branchDraft.trim().toLowerCase()); if (match) chooseBranch(match); else if (branchDraft.trim() && committedBranches.length) { setBranchCreateName(branchDraft.trim()); setBaseBranch(committedBranches.includes(branch) ? branch : committedBranches[0]); setBranchError(''); setBranchCreateOpen(true); setBranchPickerOpen(false) } } }} /><button type="button" aria-label="Show branches" onClick={() => setBranchPickerOpen((open) => !open)}><ChevronDown size={15} /></button>
                    {branchPickerOpen && <div id="git-browser-branch-options" className="git-browser-branch-options" role="listbox">
                        {branches.filter((name) => name.toLowerCase().includes(branchDraft.trim().toLowerCase())).map((name) => <button type="button" role="option" aria-selected={name === branch} key={name} onPointerDown={(event) => event.preventDefault()} onClick={() => chooseBranch(name)}>{name}</button>)}
                        {branchDraft.trim() && !branches.some((name) => name.toLowerCase() === branchDraft.trim().toLowerCase()) && committedBranches.length > 0 && <button type="button" className="git-browser-create-branch-option" onPointerDown={(event) => event.preventDefault()} onClick={() => { setBranchCreateName(branchDraft.trim()); setBaseBranch(committedBranches.includes(branch) ? branch : committedBranches[0]); setBranchError(''); setBranchCreateOpen(true); setBranchPickerOpen(false) }}><Plus size={14} /> Create branch “{branchDraft.trim()}”</button>}
                        {branchDraft.trim() && !branches.some((name) => name.toLowerCase().includes(branchDraft.trim().toLowerCase())) && !committedBranches.length && <small>Commit a file to {branches[0] ?? 'main'} before creating another branch.</small>}
                    </div>}
                </div>
            </div>
            <span>{files.length} files · {commits.length} commits</span>
            {repository.can_manage && <div className="git-browser-actions"><input ref={inputRef} type="file" multiple hidden onChange={(event) => void uploadFiles(event.target.files ?? [])} /><input ref={(node) => { folderInputRef.current = node; node?.setAttribute('webkitdirectory', '') }} type="file" multiple hidden onChange={(event) => void uploadFiles(event.target.files ?? [])} />
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => { setNewFileError(''); setNewFilePath(''); setCreateDialogOpen(true) }} disabled={saving}><Plus size={15} /> Create new</button>
                <div className="git-browser-upload-menu-wrap"><button type="button" className="entropy-button entropy-button-primary entropy-button-sm" onClick={() => setUploadMenuOpen((open) => !open)} disabled={saving}><Upload size={15} /> Upload files / folders</button>
                    {uploadMenuOpen && <div className="git-browser-upload-menu"><button type="button" onClick={() => { setUploadMenuOpen(false); inputRef.current?.click() }}><FilePlus2 size={15} /> Upload file(s)</button><button type="button" onClick={() => { setUploadMenuOpen(false); folderInputRef.current?.click() }}><FolderUp size={15} /> Upload folder</button></div>}
                </div></div>}
        </div>
        {error && <div className="entropy-alert entropy-alert-error" role="alert">{error}</div>}
        <div className="git-browser-view-tabs" role="tablist" aria-label="Repository views">
            <button type="button" role="tab" aria-selected={view === 'files'} className={view === 'files' ? 'active' : ''} onClick={() => setView('files')}><FileCode2 size={15} /> Files</button>
            <button type="button" role="tab" aria-selected={view === 'editor'} className={view === 'editor' ? 'active' : ''} onClick={() => setView('editor')} disabled={!selectedFile || selectedFile.binary}><FileCode2 size={15} /> Editor{dirty ? ' •' : ''}</button>
            {view === 'editor' && repository.can_manage && <button type="button" className="entropy-button entropy-button-primary entropy-button-sm git-browser-save" onClick={() => void saveFile()} disabled={!dirty || saving}><Save size={15} /> {saving ? 'Saving…' : isNewFile ? 'Create file' : 'Save commit'}</button>}
        </div>
        {view === 'files' ? <div className={`git-browser-file-view${dragging ? ' is-dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); if (repository.can_manage) setDragging(true) }} onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false) }} onDrop={handleDrop}>
            {dragging && <div className="git-browser-drop-hint"><Upload size={23} /> Drop files to add them to {branch}</div>}
            <div className="git-browser-file-table-wrap"><table className="git-browser-file-table"><thead><tr><th>File</th><th>Created</th><th>Created by</th><th>Modified</th><th>Modified by</th><th>Size</th></tr></thead><tbody>
                {files.map((file) => <tr key={file.path} onClick={() => void openFile(file.path)}><td><button type="button" title={file.path}><FileCode2 size={15} /> {file.path}</button></td><td>{formatDate(file.created_at)}</td><td>{file.created_by || '—'}</td><td>{formatDate(file.modified_at)}</td><td>{file.modified_by || '—'}</td><td>{file.size.toLocaleString()} B</td></tr>)}
                {!loading && !files.length && <tr><td colSpan={6} className="git-browser-empty-cell">{repository.can_manage ? 'No files yet. Add files or drag them into this area.' : 'No files in this branch yet.'}</td></tr>}
            </tbody></table></div>
            <section className="git-browser-history"><h3><GitCommitHorizontal size={16} /> Recent commits</h3>{commits.length ? commits.map((commit) => <button key={commit.sha} type="button" onClick={() => void openDiff(commit)}><strong>{commit.subject || '(no subject)'}</strong><span><code>{commit.short_sha}</code> · {commit.author} · {formatDate(commit.date)}</span></button>) : <small>No commits in this branch.</small>}</section>
            {!!commitChanges.length && <section className="git-browser-commit-diff"><header><div><h3>Compare commit changes</h3><span>Select a changed file to compare its previous and committed versions.</span></div><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setSideBySide((value) => !value)}>{sideBySide ? 'Inline diff' : 'Side-by-side diff'}</button></header>
                <div className="git-browser-change-tabs">{commitChanges.map((change) => <button type="button" key={`${change.status}:${change.path}`} className={selectedChange?.path === change.path ? 'selected' : ''} onClick={() => setSelectedChange(change)}><code>{change.status}</code>{change.path}</button>)}</div>
                {selectedChange && <><div className="git-browser-change-heading"><strong>{selectedChange.path}</strong><span>{selectedChange.status}</span></div>{selectedChange.binary ? <div className="git-browser-empty-cell">This binary or oversized file cannot be compared in the text diff viewer.</div> : <div className="git-browser-diff-view"><DiffView original={selectedChange.original} modified={selectedChange.modified} language={languageOf(selectedChange.path)} theme={theme} sideBySide={sideBySide} /></div>}</>}
            </section>}
            {loading && <div className="git-browser-loading"><LoaderCircle size={17} className="git-browser-spinner" /> Loading repository data…</div>}
        </div> : <div className="git-browser-editor-view">
            {selectedFile && !selectedFile.binary ? <><header><strong>{selectedFile.path}</strong><span>{isNewFile ? 'New file' : dirty ? 'Unsaved changes' : `${selectedFile.size.toLocaleString()} bytes`}</span></header><div className="git-browser-monaco"><Editor height="100%" language={languageOf(selectedFile.path)} value={content} theme={theme} onChange={(value) => setContent(value ?? '')} options={{ automaticLayout: true, fontSize: 13, minimap: { enabled: true }, scrollBeyondLastLine: false, tabSize: 4, renderWhitespace: 'selection', readOnly: !repository.can_manage }} /></div></> : <div className="git-browser-editor-empty">Select a text file from the Files view to open it in the editor.</div>}
        </div>}
        {createDialogOpen && <Dialog title="Create new file" subtitle={`Add a new file to the ${branch} branch.`} icon={<FilePlus2 size={18} />} onClose={() => setCreateDialogOpen(false)} footer={<><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setCreateDialogOpen(false)}>Cancel</button><button type="submit" form="git-browser-create-file-form" className="entropy-button entropy-button-primary">Create file</button></>}>
            <form id="git-browser-create-file-form" className="git-browser-create-file-form" onSubmit={createNewFile}><label>File path<input autoFocus value={newFilePath} onChange={(event) => { setNewFilePath(event.target.value); setNewFileError('') }} placeholder="src/config.json" maxLength={2048} required /></label><small>Use a relative path. You can create folders by including them in the path.</small>{newFileError && <div className="entropy-alert entropy-alert-error" role="alert">{newFileError}</div>}</form>
        </Dialog>}
        {branchCreateOpen && <Dialog title="Create branch" subtitle={`Create “${branchCreateName}” from an existing branch.`} icon={<GitBranch size={18} />} onClose={() => setBranchCreateOpen(false)} footer={<><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setBranchCreateOpen(false)}>Cancel</button><button type="submit" form="git-browser-create-branch-form" className="entropy-button entropy-button-primary" disabled={saving || !baseBranch}>{saving ? 'Creating…' : 'Create branch'}</button></>}>
            <form id="git-browser-create-branch-form" className="git-browser-create-file-form" onSubmit={(event) => void createBranch(event)}><label>New branch<input value={branchCreateName} onChange={(event) => setBranchCreateName(event.target.value)} required maxLength={255} /></label><label>Base branch<select value={baseBranch} onChange={(event) => setBaseBranch(event.target.value)} required>{committedBranches.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><small>The new branch starts at the selected branch’s latest commit.</small>{branchError && <div className="entropy-alert entropy-alert-error" role="alert">{branchError}</div>}</form>
        </Dialog>}
    </section>
}
