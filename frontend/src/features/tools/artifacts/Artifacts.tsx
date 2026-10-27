import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Archive, Check, Copy, Download, FileUp, FolderSearch, RefreshCw, Search, Tags, Trash2, Upload, X, ArrowDownWideNarrow, House, } from 'lucide-react'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import Dialog from '../../../components/layout/Dialog'
import { apiRequest, downloadFile, PROJECT_HEADER } from '../../../services/api'
import { currentProject } from '../../../services/project'
import './artifacts.css'
import EntropyLoader from '../../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../../components/feedback/useToast'

type Artifact = {
    id: number; name: string; source: 'upload' | 'server_path'; classification: 'added' | 'generated'; origin: string | null; run_id: string | null; path: string
    size_bytes: number; sha256: string | null; tags: string[]; created_by: string; created_at: string
    download_url: string | null
}
type ArtifactData = { items: Artifact[]; permissions: { 'artifacts.write': boolean } }

const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    const units = ['KB', 'MB', 'GB', 'TB']
    let value = bytes / 1024, index = 0
    while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1 }
    return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`
}

export default function Artifacts() {
    const { notify, modal } = useFeedback()
    const [data, setData] = useState<ArtifactData | null>(null)
    const [path, setPath] = useState('')
    const [tags, setTags] = useState('')
    const [query, setQuery] = useState('')
    const [classification, setClassification] = useState<'added' | 'generated'>('added')
    const [activeTag, setActiveTag] = useState<string | null>(null)
    const [sort, setSort] = useState('created_desc')
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
    const [housekeepingOpen, setHousekeepingOpen] = useState(false)
    const [housekeepingDays, setHousekeepingDays] = useState('30')
    const [housekeepingTag, setHousekeepingTag] = useState('')
    const [editingTagsId, setEditingTagsId] = useState<number | null>(null)
    const [tagDraft, setTagDraft] = useState('')
    const [busy, setBusy] = useState(false)
    const [dragging, setDragging] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)
    const inputRef = useRef<HTMLInputElement>(null)

    const refresh = useCallback(async () => {
        const response = await apiRequest<ArtifactData>('/api/artifacts')
        setData(response)
        setError('')
    }, [])

    const visibleItems = useMemo(() => {
        const needle = query.trim().toLocaleLowerCase()
        const classified = (data?.items ?? []).filter((artifact) => artifact.classification === classification)
        const searched = classified.filter((artifact) => !needle ||
            artifact.name.toLocaleLowerCase().includes(needle) ||
            artifact.tags.some((tag) => tag.toLocaleLowerCase().includes(needle)),
        )
        const tagged = activeTag ? searched.filter((artifact) => artifact.tags.includes(activeTag)) : searched
        return tagged.sort((a, b) => {
            if (sort === 'name_asc') return a.name.localeCompare(b.name)
            if (sort === 'name_desc') return b.name.localeCompare(a.name)
            if (sort === 'size_asc') return a.size_bytes - b.size_bytes
            if (sort === 'size_desc') return b.size_bytes - a.size_bytes
            const dateOrder = a.created_at.localeCompare(b.created_at)
            return sort === 'created_asc' ? dateOrder : -dateOrder
        })
    }, [data, query, classification, activeTag, sort])

    const addedCount = data?.items.filter((artifact) => artifact.classification === 'added').length ?? 0
    const generatedCount = data?.items.filter((artifact) => artifact.classification === 'generated').length ?? 0
    const selectedVisibleIds = visibleItems.filter((artifact) => selectedIds.has(artifact.id)).map((artifact) => artifact.id)
    const generatedGroups = useMemo(() => {
        if (classification !== 'generated') return [{ key: '', label: '', items: visibleItems }]
        const groups = new Map<string, Artifact[]>()
        for (const artifact of visibleItems) {
            const key = artifact.run_id || artifact.tags.find((tag) => tag.startsWith('run:')) || 'legacy'
            groups.set(key, [...(groups.get(key) ?? []), artifact])
        }
        return [...groups.entries()].map(([key, items]) => ({
            key,
            label: key === 'legacy' ? 'Generated files' : `Execution ${items[0]?.tags.find((tag) => tag.startsWith('run:')) ?? key}`,
            items,
        }))
    }, [classification, visibleItems])

    useEffect(() => {
        void refresh().catch((reason: Error) => setError(reason.message))
    }, [refresh])

    const uploadFiles = async (files: FileList | File[]) => {
        const selected = Array.from(files)
        if (!selected.length) return
        setBusy(true)
        try {
            for (const file of selected) {
                const form = new FormData()
                form.append('file', file, file.name)
                form.append('tags', tags)
                await apiRequest<Artifact>('/api/artifacts/upload', { method: 'POST', body: form })
            }
            await refresh()
            setTags('')
            notify.success(`${selected.length} package${selected.length === 1 ? '' : 's'} uploaded to Entropy.`, { title: 'Upload complete' })
        } catch (reason) {
            notify.error((reason as Error).message, { title: 'Unable to upload package' })
            await refresh().catch(() => undefined)
        } finally { setBusy(false) }
    }

    const registerPath = async (event: FormEvent) => {
        event.preventDefault()
        if (!path.trim()) return
        setBusy(true)
        try {
            await apiRequest<Artifact>('/api/artifacts/server-path', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path.trim(), tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean) }),
            })
            setPath(''); setTags(''); await refresh()
            notify.success('Server package added to the artifact list.', { title: 'Artifact registered' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to register server path' }) }
        finally { setBusy(false) }
    }

    const download = async (artifact: Artifact) => {
        if (!artifact.download_url) return
        try {
            const project = currentProject()
            const response = await fetch(artifact.download_url, {
                credentials: 'same-origin', cache: 'no-store',
                headers: project ? { [PROJECT_HEADER]: project } : undefined,
            })
            if (!response.ok) throw new Error(`Download failed (${response.status}).`)
            const url = URL.createObjectURL(await response.blob())
            const link = document.createElement('a'); link.href = url; link.download = artifact.name; link.click()
            URL.revokeObjectURL(url)
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to download artifact' }) }
    }

    const copyPath = async (artifact: Artifact) => {
        try { await navigator.clipboard.writeText(artifact.path); notify.success('Artifact path copied.', { title: 'Copied' }) }
        catch (reason) { notify.error((reason as Error).message, { title: 'Unable to copy path' }) }
    }

    const saveTags = async (event: FormEvent, artifact: Artifact) => {
        event.preventDefault()
        const nextTags = tagDraft.split(',').map((tag) => tag.trim()).filter(Boolean)
        try {
            await apiRequest(`/api/artifacts/${artifact.id}/tags`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tags: nextTags }),
            })
            setEditingTagsId(null); await refresh()
            notify.success('Artifact tags updated.', { title: 'Tags saved' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to update tags' }) }
    }

    const remove = async (artifact: Artifact) => {
        const confirmed = await modal.confirm({
            title: 'Remove artifact?',
            message: `Remove ${artifact.name} from this project? Uploaded data will be deleted from Entropy. A server file will be left in place.`,
            confirmText: 'Remove', destructive: true,
        })
        if (!confirmed) return
        try {
            await apiRequest(`/api/artifacts/${artifact.id}`, { method: 'DELETE' })
            await refresh(); notify.success('Artifact removed from the project.', { title: 'Artifact removed' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to remove artifact' }) }
    }

    const removeSelected = async () => {
        if (!selectedVisibleIds.length) return
        const confirmed = await modal.confirm({ title: 'Remove selected artifacts?', message: `Remove ${selectedVisibleIds.length} selected artifacts? Uploaded data is deleted; server files are left in place.`, confirmText: 'Remove selected', destructive: true })
        if (!confirmed) return
        try {
            const result = await apiRequest<{ deleted: number }>('/api/artifacts/bulk-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ artifact_ids: selectedVisibleIds }) })
            setSelectedIds(new Set()); await refresh()
            notify.success(`${result.deleted} artifact${result.deleted === 1 ? '' : 's'} removed.`, { title: 'Artifacts removed' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to remove artifacts' }) }
    }

    const downloadSelected = async () => {
        if (!selectedVisibleIds.length) return
        try {
            await downloadFile('/api/artifacts/bulk-download', { artifact_ids: selectedVisibleIds }, 'entropy-artifacts.zip')
            notify.success('Selected artifacts downloaded.', { title: 'Download ready' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to download artifacts' }) }
    }

    const runHousekeeping = async (event: FormEvent) => {
        event.preventDefault()
        const days = Number(housekeepingDays)
        if (!Number.isInteger(days) || days < 1) return
        const confirmed = await modal.confirm({ title: 'Run artifact housekeeping?', message: `Delete ${classification} artifacts older than ${days} days${housekeepingTag.trim() ? ` tagged “${housekeepingTag.trim()}”` : ''}? Server files will be left in place.`, confirmText: 'Delete matching artifacts', destructive: true })
        if (!confirmed) return
        setBusy(true)
        try {
            const result = await apiRequest<{ deleted: number }>('/api/artifacts/housekeeping', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ older_than_days: days, classification, tag: housekeepingTag.trim() }) })
            setHousekeepingOpen(false); setSelectedIds(new Set()); await refresh()
            notify.success(`${result.deleted} artifact${result.deleted === 1 ? '' : 's'} deleted by housekeeping.`, { title: 'Housekeeping complete' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to run housekeeping' }) }
        finally { setBusy(false) }
    }

    const toggleSelected = (id: number) => setSelectedIds((current) => {
        const next = new Set(current)
        if (next.has(id)) next.delete(id); else next.add(id)
        return next
    })

    const renderArtifact = (artifact: Artifact) => <article className="artifact-row" key={artifact.id}>
        <input className="artifact-select" type="checkbox" aria-label={`Select ${artifact.name}`} checked={selectedIds.has(artifact.id)} onChange={() => toggleSelected(artifact.id)} />
        <span className="artifact-file-icon"><Archive size={18} /></span>
        <div className="artifact-main"><strong title={artifact.name}>{artifact.name}</strong><span>{artifact.classification === 'generated' ? `Generated by ${artifact.origin || 'Entropy workflow/plugin'}` : artifact.source === 'upload' ? 'Uploaded to Entropy' : 'Existing server file'} · {formatBytes(artifact.size_bytes)} · {artifact.classification === 'generated' ? 'Generated' : `Added by ${artifact.created_by}`}</span><code title={artifact.path}>{artifact.path}</code>
            {editingTagsId === artifact.id ? <form className="artifact-tag-editor" onSubmit={(event) => void saveTags(event, artifact)}><Tags size={14} /><input autoFocus value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} aria-label={`Edit tags for ${artifact.name}`} placeholder="comma-separated tags" /><button type="submit" className="entropy-button entropy-button-ghost entropy-button-sm" title="Save tags"><Check size={15} /></button><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setEditingTagsId(null)} title="Cancel"><X size={15} /></button></form> : artifact.tags.length ? <div className="artifact-tags">{artifact.tags.map((tag) => <button type="button" className={activeTag === tag ? 'is-active' : ''} key={tag} onClick={() => { setActiveTag(activeTag === tag ? null : tag); setQuery('') }} title={`Show artifacts tagged ${tag}`}>{tag}</button>)}</div> : <span className="artifact-no-tags">No tags</span>}
        </div>
        <div className="artifact-actions"><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => void copyPath(artifact)} title="Copy server path"><Copy size={15} /></button><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void download(artifact)} title="Download package"><Download size={15} /></button>{data?.permissions['artifacts.write'] && <><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => { setEditingTagsId(artifact.id); setTagDraft(artifact.tags.join(', ')) }} title="Edit tags"><Tags size={15} /></button><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => void remove(artifact)} title="Remove artifact"><Trash2 size={15} /></button></>}</div>
    </article>

    const onDrop = (event: DragEvent<HTMLDivElement>) => {
        event.preventDefault(); setDragging(false)
        if (data?.permissions['artifacts.write'] && !busy) void uploadFiles(event.dataTransfer.files)
    }

    return <section className="artifacts-tool">
        <header className="artifacts-heading">
            <div><span className="artifacts-mark"><Archive size={21} /></span><div><h3>Release artifacts</h3><p>Keep deployable packages with the active project or register files already on the Entropy server.</p></div></div>
            <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void refresh()} title="Refresh artifacts"><RefreshCw size={15} /></button>
        </header>


        {data?.permissions['artifacts.write'] && <div className="artifacts-ingest">
            <div className={`artifacts-dropzone${dragging ? ' is-dragging' : ''}${busy ? ' is-busy' : ''}`}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false) }}
                onDrop={onDrop}>
                <FileUp size={25} />
                <strong>{busy ? 'Working…' : 'Drop release packages here'}</strong>
                <span>or select one or more files to upload into Entropy.</span>
                <label className="artifacts-ingest-tags">Tags <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="release, 2.8.0, production" disabled={busy} /></label>
                <button type="button" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy} onClick={() => inputRef.current?.click()}><Upload size={15} /> Choose files</button>
                <input ref={inputRef} type="file" multiple hidden disabled={busy} onChange={(event) => { if (event.currentTarget.files) void uploadFiles(event.currentTarget.files); event.currentTarget.value = '' }} />
            </div>
            <form className="artifacts-path-form" onSubmit={(event) => void registerPath(event)}>
                <label htmlFor="artifact-server-path"><FolderSearch size={17} /> Register a file already on the Entropy server</label>
                <div><input id="artifact-server-path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="/app/releases/product/product-2.8.0.war" disabled={busy} /><button type="submit" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={busy || !path.trim()}>Add path</button></div>
                <label className="artifacts-path-tags">Tags <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="release, 2.8.0, production" disabled={busy} /></label>
                <small>Enter an absolute path that the Entropy service account can read. The file stays at that location.</small>
            </form>
        </div>}

        {!data ? <EntropyLoader label="Loading artifacts…" /> : <>
            <nav className="artifacts-tabs" aria-label="Artifact classification">
                <button type="button" className={classification === 'added' ? 'is-active' : ''} onClick={() => { setClassification('added'); setSelectedIds(new Set()); setActiveTag(null) }}>Added <span>{addedCount}</span></button>
                <button type="button" className={classification === 'generated' ? 'is-active' : ''} onClick={() => { setClassification('generated'); setSelectedIds(new Set()); setActiveTag(null) }}>Generated <span>{generatedCount}</span></button>
            </nav>
            <div className="artifacts-controls">
                <label className="artifacts-search"><Search size={17} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by filename or tag" aria-label="Search artifacts by filename or tag" /></label>
                <label className="artifacts-sort"><ArrowDownWideNarrow size={16} /><span>Sort</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="created_desc">Newest first</option><option value="created_asc">Oldest first</option><option value="name_asc">Name A–Z</option><option value="name_desc">Name Z–A</option><option value="size_desc">Largest first</option><option value="size_asc">Smallest first</option></select></label>
                {data.permissions['artifacts.write'] && <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setHousekeepingOpen(true)}><House size={15} /> Housekeeping</button>}
            </div>
            {activeTag && <button type="button" className="artifacts-tag-filter" onClick={() => setActiveTag(null)}>Filtered by <strong>{activeTag}</strong><X size={14} /></button>}
            <div className="artifacts-bulkbar"><label><input type="checkbox" checked={visibleItems.length > 0 && selectedVisibleIds.length === visibleItems.length} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); visibleItems.forEach((item) => event.target.checked ? next.add(item.id) : next.delete(item.id)); return next })} /> Select visible ({visibleItems.length})</label>{selectedVisibleIds.length > 0 && <><span>{selectedVisibleIds.length} selected</span><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void downloadSelected()}><Download size={15} /> Download selected</button>{data.permissions['artifacts.write'] && <button type="button" className="entropy-button entropy-button-danger entropy-button-sm" onClick={() => void removeSelected()}><Trash2 size={15} /> Delete selected</button>}</>}</div>
            {visibleItems.length ? <div className="artifacts-list">{generatedGroups.map((group) => <section className="artifact-run-group" key={group.key || 'added'}>{group.label && <h4>{group.label} <span>{group.items.length} file{group.items.length === 1 ? '' : 's'}</span></h4>}{group.items.map(renderArtifact)}</section>)}</div> : query.trim() || activeTag ? <div className="artifacts-empty"><Search size={25} /><strong>No matching artifacts</strong><span>Try a different filename or tag.</span></div> : <div className="artifacts-empty"><Archive size={27} /><strong>{classification === 'added' ? 'No added artifacts yet' : 'No generated artifacts yet'}</strong><span>{classification === 'added' ? 'Upload a package or register its path on the Entropy server.' : 'Files declared by workflow or plugin runs will appear here.'}</span></div>}
        </>}
        {housekeepingOpen && <Dialog title="Artifact housekeeping" subtitle={`Delete older ${classification} artifacts using a retention rule. Uploaded files are removed from Entropy; registered server files remain on disk.`} icon={<House size={18} />} onClose={() => setHousekeepingOpen(false)} footer={<><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setHousekeepingOpen(false)}>Cancel</button><button type="submit" form="artifact-housekeeping-form" className="entropy-button entropy-button-danger" disabled={busy || !Number(housekeepingDays)}>{busy ? 'Deleting…' : 'Delete matching artifacts'}</button></>}>
            <form id="artifact-housekeeping-form" className="artifact-housekeeping-form" onSubmit={(event) => void runHousekeeping(event)}><label>Delete artifacts older than (days)<input type="number" min="1" max="36500" value={housekeepingDays} onChange={(event) => setHousekeepingDays(event.target.value)} required /></label><label>Optional tag rule<input value={housekeepingTag} onChange={(event) => setHousekeepingTag(event.target.value)} placeholder="Only delete artifacts with this exact tag" /></label><small>Leave the tag empty to delete all matching artifacts in the {classification} tab that exceed the age limit.</small></form>
        </Dialog>}
    </section>
}
