import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Archive, ArrowUpRight, Clipboard, Download, FileJson2, FileSpreadsheet, ListPlus, MapPin, PackageCheck, Play, Plus, RefreshCw, Search, Settings2, Upload, Workflow as WorkflowIcon, X } from 'lucide-react'
import { currentProject } from '../../../services/project'
import { copyRich, outlookReport, releaseLabel, releaseRows, taskRows, taskStatus } from './outlook'
import { apiRequest } from '../../../services/api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import './release-manager.css'
import EntropyLoader from '../../../components/feedback/EntropyLoader'
import Pagination from '../../../components/layout/Pagination'
import { usePagination } from '../../../components/layout/usePagination'

type Stage = 'workflow_queue' | 'workflow_done' | 'task_queue' | 'completed'
export type ReleaseTask = {
    id: number; key?: string | null; title: string; description?: string; remarks?: string; status: string; assignee: string | null
    assigned_by?: string | null; assigned_at?: string | null; external_ref?: string | null; attachment_count?: number
    group_names?: string | null; comments?: { author: string; body: string; created_at: string }[]
}
export type Release = {
    id: number; name: string; version: string; environment: string; description: string
    workflow_name: string; workflow_job_id: number | null; workflow_state: string | null
    stage: Stage; created_by: string; created_at: string; updated_at: string; archived_at?: string | null
    tags: string[]; artifacts: { id: number; name: string; source: string; size_bytes: number }[]; tasks: ReleaseTask[]
}
type Workflow = { name: string; version: string; description: string }
export type Promotion = {
    id: number; promotion_number: string; target_environment: string; workflow_name: string; workflow_job_id: number | null
    workflow_state?: string; status: string; created_by: string; created_at: string; archived_at?: string | null
    releases: { id: number; name: string; version: string; environment: string }[]
}
type Data = {
    items: Release[]; promotions: Promotion[]; workflows: Workflow[]
    environments: string[]; housekeeping_rules: HousekeepingRule[]
    permissions: { 'releases.create': boolean; 'releases.manage': boolean; 'releases.promote': boolean; 'workflows.execute': boolean; 'tasks.create': boolean; 'artifacts.read': boolean }
}
type HousekeepingRule = { entity: 'release' | 'promotion'; older_than_days: number; statuses: string[] }
type Artifact = { id: number; name: string; size_bytes: number }
type ProjectTaskData = { items: { id: number; key?: string; title: string }[]; members: { username: string; full_name: string | null }[] }
type ReleaseDraft = { name: string; version: string; environment: string; description: string; workflow_name: string; tags: string; artifact_ids: number[] }
type TaskDraft = { title: string; description: string; remarks: string; assignee: string }

const stages: { id: Stage; label: string }[] = [
    { id: 'workflow_queue', label: 'Workflow queue' },
    { id: 'workflow_done', label: 'Workflow done' },
    { id: 'task_queue', label: 'Task queue' },
    { id: 'completed', label: 'Completed' },
]
const blankRelease: ReleaseDraft = { name: '', version: '', environment: '', description: '', workflow_name: '', tags: '', artifact_ids: [] }
const blankTask: TaskDraft = { title: '', description: '', remarks: '', assignee: '' }
const readable = (value: string) => value.replaceAll('_', ' ')

function ReleaseModalLayer({ children, onClose }: { children: ReactNode; onClose: () => void }) {
    const host = document.querySelector('.entropy-app') ?? document.body
    return createPortal(
        <div className="release-modal-backdrop" role="presentation" onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose()
        }}>{children}</div>,
        host,
    )
}

export default function ReleaseManager() {
    const { notify } = useFeedback()
    const notifyErrorRef = useRef(notify.error)
    const [data, setData] = useState<Data | null>(null)
    const [selectedId, setSelectedId] = useState<number | null>(null)
    const [tab, setTab] = useState<'releases' | 'promotions' | 'history'>('releases')
    const [creating, setCreating] = useState(false)
    const [draft, setDraft] = useState<ReleaseDraft>(blankRelease)
    const [taskDraft, setTaskDraft] = useState<TaskDraft>(blankTask)
    const [showTaskForm, setShowTaskForm] = useState(false)
    const [promotionWorkflow, setPromotionWorkflow] = useState('')
    const [runWorkflows, setRunWorkflows] = useState<Record<number, string>>({})
    const [environmentEdit, setEnvironmentEdit] = useState<{ id: number; value: string } | null>(null)
    const [newEnvironment, setNewEnvironment] = useState('')
    const [targetEnvironment, setTargetEnvironment] = useState('')
    const [promotionNumber, setPromotionNumber] = useState('')
    const [promotionReleaseIds, setPromotionReleaseIds] = useState<Set<number>>(new Set())
    const [selectedReleaseIds, setSelectedReleaseIds] = useState<Set<number>>(new Set())
    const [selectedPromotionIds, setSelectedPromotionIds] = useState<Set<number>>(new Set())
    const [showArchived, setShowArchived] = useState(false)
    const [releaseSearch, setReleaseSearch] = useState('')
    const [releaseSort, setReleaseSort] = useState<'newest' | 'name' | 'updated' | 'environment'>('newest')
    const [artifacts, setArtifacts] = useState<Artifact[]>([])
    const [housekeepingOpen, setHousekeepingOpen] = useState(false)
    const [housekeepingRules, setHousekeepingRules] = useState<HousekeepingRule[]>([])
    const [housekeepingDraft, setHousekeepingDraft] = useState<HousekeepingRule>({ entity: 'release', older_than_days: 30, statuses: ['completed'] })
    const [traceabilityOpen, setTraceabilityOpen] = useState(false)
    const [traceabilityView, setTraceabilityView] = useState<'releases' | 'tasks'>('releases')
    const [existingTasks, setExistingTasks] = useState<{ id: number; key?: string; title: string }[]>([])
    const [projectMembers, setProjectMembers] = useState<ProjectTaskData['members']>([])
    const [linkTaskId, setLinkTaskId] = useState('')
    const [busy, setBusy] = useState(false)
    const [traceabilityMenu, setTraceabilityMenu] = useState(false)
    const [combinedTraceabilityMenu, setCombinedTraceabilityMenu] = useState(false)
    const selected = data?.items.find((item) => item.id === selectedId) ?? null

    const refresh = useCallback(async () => {
        const result = await apiRequest<Data>(`/api/releases${showArchived ? '?include_archived=true' : ''}`)
        setData(result)
        setSelectedId((id) => id && result.items.some((item) => item.id === id) ? id : null)
        setPromotionWorkflow((current) => current || result.workflows[0]?.name || '')
        setHousekeepingRules(result.housekeeping_rules ?? [])
        if (result.permissions['artifacts.read']) {
            void apiRequest<{ items: Artifact[] }>('/api/artifacts').then((artifactData) => setArtifacts(artifactData.items)).catch(() => setArtifacts([]))
        }
    }, [showArchived])

    useEffect(() => { void refresh().catch((reason: Error) => notifyErrorRef.current(reason.message, { title: 'Unable to load releases' })) }, [refresh])
    const hasActiveRuns = Boolean(data?.items.some((item) => ['queued', 'starting', 'running', 'paused'].includes(item.workflow_state ?? '')) ||
        data?.promotions.some((item) => item.status === 'running'))
    useEffect(() => {
        if (!hasActiveRuns) return
        const timer = window.setInterval(() => { void refresh().catch(() => undefined) }, 5000)
        return () => window.clearInterval(timer)
    }, [hasActiveRuns, refresh])
    useEffect(() => {
        if (!selected || !data?.permissions['tasks.create']) return
        void apiRequest<ProjectTaskData>('/api/tasks')
            .then((result) => {
                setExistingTasks(result.items.filter((task) => !selected.tasks.some((linked) => linked.id === task.id)))
                setProjectMembers(result.members)
            })
            .catch(() => setExistingTasks([]))
    }, [selected?.id, selected?.tasks.length, data?.permissions['tasks.create']])

    const environmentDraft = selected && environmentEdit?.id === selected.id ? environmentEdit.value : selected?.environment ?? ''
    const setEnvironmentDraft = (value: string) => selected && setEnvironmentEdit({ id: selected.id, value })

    const archivedFilter = useCallback((item: { archived_at?: string | null }) => Boolean(item.archived_at) === showArchived, [showArchived])
    const visibleReleases = useMemo(() => (data?.items ?? []).filter(archivedFilter).filter((item) => {
        const needle = releaseSearch.trim().toLowerCase()
        return !needle || [item.name, item.version, item.environment, item.workflow_name, ...item.tags].some((value) => value.toLowerCase().includes(needle))
    }).sort((left, right) => releaseSort === 'name' ? left.name.localeCompare(right.name) : releaseSort === 'environment' ? left.environment.localeCompare(right.environment) : releaseSort === 'updated' ? right.updated_at.localeCompare(left.updated_at) : right.id - left.id), [data, releaseSearch, releaseSort, archivedFilter])
    const completed = useMemo(() => visibleReleases.filter((item) => item.stage === 'completed'), [visibleReleases])
    const visiblePromotions = useMemo(() => (data?.promotions ?? []).filter(archivedFilter), [data, archivedFilter])
    const historyPromotions = useMemo(() => visiblePromotions.filter((item) => item.status !== 'queued'), [visiblePromotions])
    const queuedPromotions = useMemo(() => visiblePromotions.filter((item) => item.status === 'queued'), [visiblePromotions])
    const releasePages = usePagination(visibleReleases, 'releases')
    const queuedPages = usePagination(queuedPromotions, 'release-promotions')
    const historyPages = usePagination(historyPromotions, 'release-promotion-history')
    const setReleaseField = (key: keyof ReleaseDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }))
    const setTaskField = (key: keyof TaskDraft, value: string) => setTaskDraft((current) => ({ ...current, [key]: value }))

    const toggleArchiveSelection = (id: number, kind: 'release' | 'promotion') => {
        const update = kind === 'release' ? setSelectedReleaseIds : setSelectedPromotionIds
        update((current) => {
            const next = new Set(current)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
        })
    }

    const archiveSelected = async (kind: 'release' | 'promotion') => {
        const releaseIds = kind === 'release' ? [...selectedReleaseIds] : []
        const promotionIds = kind === 'promotion' ? [...selectedPromotionIds] : []
        if (!releaseIds.length && !promotionIds.length) return
        setBusy(true)
        try {
            const result = await apiRequest<{ archived_releases: number; archived_promotions: number }>('/api/releases/archive', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ release_ids: releaseIds, promotion_ids: promotionIds }),
            })
            setSelectedReleaseIds(new Set())
            setSelectedPromotionIds(new Set())
            if (releaseIds.includes(selectedId ?? -1)) setSelectedId(null)
            await refresh()
            const count = result.archived_releases + result.archived_promotions
            notify.success(`${count} record${count === 1 ? '' : 's'} archived. No data was deleted.`, { title: 'Archive complete' })
        } catch (reason) {
            notify.error((reason as Error).message, { title: 'Unable to archive records' })
        } finally { setBusy(false) }
    }

    const createRelease = async (event: FormEvent) => {
        event.preventDefault()
        setBusy(true)
        try {
            const created = await apiRequest<Release>('/api/releases', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...draft, name: draft.name.trim(), workflow_name: draft.workflow_name,
                    tags: draft.tags.split(',').map((tag) => tag.trim()).filter(Boolean) }),
            })
            setCreating(false); setDraft(blankRelease); await refresh(); setSelectedId(created.id)
            notify.success('Release created.', { title: 'Release Manager' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to create release' }) } finally { setBusy(false) }
    }

    const exportReleases = () => {
        const payload = {
            format: 'entropy.release-manager.v1',
            exported_at: new Date().toISOString(),
            releases: (data?.items ?? []).map(({ name, version, environment, description, workflow_name, tags, tasks }) => ({
                name, version, environment, description, workflow_name, tags,
                tasks: tasks.map(({ title, status, assignee }) => ({ title, status, assignee })),
            })),
        }
        const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
        const link = window.document.createElement('a'); link.href = url; link.download = 'entropy-releases.json'; link.click()
        URL.revokeObjectURL(url)
        notify.success('Release data downloaded as JSON.', { title: 'Export complete' })
    }

    const importReleases = async (file?: File) => {
        if (!file || !data) return
        setBusy(true)
        try {
            const parsed = JSON.parse(await file.text()) as { releases?: unknown[] } | unknown[]
            const items = Array.isArray(parsed) ? parsed : parsed.releases
            if (!Array.isArray(items) || !items.length) throw new Error('Release JSON must be an array or contain a releases array.')
            for (const entry of items) {
                if (!entry || typeof entry !== 'object') throw new Error('Each imported release must be an object.')
                const release = entry as Record<string, unknown>
                const name = String(release.name ?? '').trim()
                const workflow_name = String(release.workflow_name ?? '').trim()
                if (!name || !workflow_name) throw new Error('Every release needs a name and workflow_name.')
                if (!data.workflows.some((workflow) => workflow.name === workflow_name)) throw new Error(`Workflow '${workflow_name}' is not available in the active project.`)
                const created = await apiRequest<Release>('/api/releases', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, workflow_name, version: String(release.version ?? ''), environment: String(release.environment ?? ''), description: String(release.description ?? ''), tags: Array.isArray(release.tags) ? release.tags.map(String) : [] }),
                })
                const tasks = Array.isArray(release.tasks) ? release.tasks.flatMap((value) => {
                    if (!value || typeof value !== 'object') return []
                    const task = value as Record<string, unknown>
                    const title = String(task.title ?? task.summary ?? '').trim()
                    return title ? [{ title, description: String(task.description ?? ''), remarks: String(task.remarks ?? ''), assignee: null }] : []
                }) : []
                if (tasks.length) await apiRequest(`/api/releases/${created.id}/tasks/import`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tasks }),
                })
            }
            await refresh()
            notify.success(`${items.length} release${items.length === 1 ? '' : 's'} imported.`, { title: 'Import complete' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to import releases' }) } finally { setBusy(false) }
    }

    const updateStage = async (release: Release, stage: Stage) => {
        try {
            await apiRequest(`/api/releases/${release.id}`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stage }),
            })
            await refresh()
            notify.success('Release stage updated.', { title: 'Release Manager' })
        } catch (reason) {
            notify.error((reason as Error).message, { title: 'Unable to update release stage' })
        }
    }

    const runWorkflow = async (release: Release) => {
        setBusy(true)
        try { await apiRequest(`/api/releases/${release.id}/run`, { method: 'POST' }); await refresh(); notify.success('Release workflow started.', { title: 'Workflow started' }) }
        catch (reason) { notify.error((reason as Error).message, { title: 'Unable to start release workflow' }) } finally { setBusy(false) }
    }

    const addTask = async (event: FormEvent) => {
        event.preventDefault()
        if (!selected) return
        setBusy(true)
        try {
            await apiRequest(`/api/releases/${selected.id}/tasks`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...taskDraft, title: taskDraft.title.trim(), assignee: taskDraft.assignee || null }),
            })
            setTaskDraft(blankTask); setShowTaskForm(false); await refresh()
            notify.success('Task linked to the release.', { title: 'Task created' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to create linked task' }) } finally { setBusy(false) }
    }

    const importTasks = async (file?: File) => {
        if (!file || !selected) return
        try {
            const parsed: unknown = JSON.parse(await file.text())
            const tasks = Array.isArray(parsed) ? parsed : (parsed as { tasks?: unknown[] } | null)?.tasks
            if (!Array.isArray(tasks) || tasks.length === 0) throw new Error('JSON must be an array of tasks or an object with a tasks array.')
            await apiRequest(`/api/releases/${selected.id}/tasks/import`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tasks }),
            })
            await refresh()
            notify.success(`${tasks.length} linked task${tasks.length === 1 ? '' : 's'} imported.`, { title: 'Import complete' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to import linked tasks' }) }
    }

    const linkExistingTask = async () => {
        if (!selected || !linkTaskId) return
        try {
            await apiRequest(`/api/releases/${selected.id}/tasks/link`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_ids: [Number(linkTaskId)] }),
            })
            setLinkTaskId(''); await refresh()
            notify.success('Task linked to the release.', { title: 'Task linked' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to link task' }) }
    }

    const unlinkTask = async (taskId: number) => {
        if (!selected) return
        try { await apiRequest(`/api/releases/${selected.id}/tasks/${taskId}`, { method: 'DELETE' }); await refresh(); notify.success('Task unlinked from the release.', { title: 'Task unlinked' }) }
        catch (reason) { notify.error((reason as Error).message, { title: 'Unable to unlink task' }) }
    }

    const downloadWorkbook = (ids: number[]) => {
        const params = new URLSearchParams()
        if (ids.length) params.set('ids', ids.join(','))
        if (showArchived) params.set('include_archived', 'true')
        const project = currentProject()
        if (project) params.set('project', project)
        const link = window.document.createElement('a')
        link.href = `/api/releases/report.xlsx?${params.toString()}`
        link.click()
        notify.success('The Excel report has Summary (pivot tables), Releases and Tasks sheets.', { title: 'Excel report' })
    }

    const exportTraceabilityExcel = () => {
        if (!selected) return
        setTraceabilityMenu(false)
        downloadWorkbook([selected.id])
    }

    const copyReport = async (releases: Release[], heading: string) => {
        const { html, plain } = outlookReport(heading, releases, data?.promotions ?? [])
        try {
            await copyRich(html, plain)
            notify.success('Paste it into an Outlook message: the release and task tables keep their layout.', { title: 'Report copied' })
        } catch (reason) {
            notify.error((reason as Error).message, { title: 'Unable to copy report' })
        }
    }

    const copyTraceabilityReport = async () => {
        if (!selected) return
        setTraceabilityMenu(false)
        await copyReport([selected], `Release status: ${releaseLabel(selected)}`)
    }

    const traceabilityRows = () => ({
        releaseRows: releaseRows(visibleReleases, data?.promotions ?? []),
        taskRows: taskRows(visibleReleases),
    })

    const exportCombinedTraceabilityExcel = () => {
        if (!visibleReleases.length) return
        setTraceabilityOpen(false)
        downloadWorkbook(visibleReleases.map((release) => release.id))
    }

    const copyCombinedTraceabilityReport = async () => {
        if (!visibleReleases.length) return
        await copyReport(visibleReleases, 'Release traceability')
        setTraceabilityOpen(false)
    }

    const saveEnvironment = async (release: Release) => {
        const environment = environmentDraft.trim()
        if (environment === release.environment) return
        try {
            await apiRequest(`/api/releases/${release.id}`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ environment }),
            })
            setEnvironmentEdit(null); await refresh()
            notify.success(environment ? `${releaseLabel(release)} is in ${environment}.` : 'Environment cleared.', { title: 'Environment updated' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to update the environment' }) }
    }

    const addEnvironment = async () => {
        const name = newEnvironment.trim()
        if (!name) return
        try {
            await apiRequest('/api/releases/environments', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
            })
            setNewEnvironment(''); await refresh()
            notify.success(`${name} can now be chosen for releases and promotions.`, { title: 'Environment added' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to add the environment' }) }
    }

    const createPromotionRecord = async () => {
        if (!data || !promotionReleaseIds.size || !targetEnvironment.trim()) return
        setBusy(true)
        try {
            const result = await apiRequest<{ promotion: Promotion }>('/api/releases/promotions', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ release_ids: [...promotionReleaseIds], target_environment: targetEnvironment.trim(), promotion_number: promotionNumber.trim() || null, workflow_name: promotionWorkflow }),
            })
            setPromotionReleaseIds(new Set()); setPromotionNumber(''); setTab('promotions'); await refresh()
            notify.success(`Promotion ${result.promotion.promotion_number} is ready in the promotion queue.`, { title: 'Promotion created' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to create promotion' }) } finally { setBusy(false) }
    }

    const workflowFor = (promotion: Promotion) => runWorkflows[promotion.id] ?? promotion.workflow_name ?? ''
    const runPromotion = async (promotion: Promotion) => {
        const workflow = workflowFor(promotion)
        if (!workflow) return
        setBusy(true)
        try {
            await apiRequest(`/api/releases/promotions/${promotion.id}/run`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workflow_name: workflow }),
            })
            await refresh()
            notify.success(`${workflow} is promoting ${promotion.promotion_number} to ${promotion.target_environment}.`, { title: 'Promotion started' })
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to start promotion' }) } finally { setBusy(false) }
    }

    const togglePromotionRelease = (id: number) => setPromotionReleaseIds((current) => {
        const next = new Set(current)
        if (next.has(id)) next.delete(id); else next.add(id)
        return next
    })

    const saveHousekeeping = async (runNow = false) => {
        setBusy(true)
        try {
            await apiRequest('/api/releases/housekeeping', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rules: housekeepingRules }),
            })
            if (runNow) {
                const result = await apiRequest<{ archived: number }>('/api/releases/housekeeping/run', { method: 'POST' })
                notify.success(`${result.archived} release or promotion record${result.archived === 1 ? '' : 's'} archived.`, { title: 'Housekeeping complete' })
            } else notify.success('Archive rules saved.', { title: 'Housekeeping' })
            setHousekeepingOpen(false)
            await refresh()
        } catch (reason) { notify.error((reason as Error).message, { title: 'Unable to save archive rules' }) }
        finally { setBusy(false) }
    }

    const addHousekeepingRule = () => {
        setHousekeepingRules((current) => [...current, { ...housekeepingDraft, statuses: [...housekeepingDraft.statuses] }])
    }

    return <div className="release-manager">
        <header className="release-manager-header">
            <div><span className="release-manager-mark"><PackageCheck size={21} /></span><div><h3>Release Manager</h3><p>Coordinate workflow releases, task queues and environment promotions.</p></div></div>
            <div className="release-actions">
                <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void refresh()} title="Refresh"><RefreshCw size={15} /></button>
                {data?.permissions['releases.manage'] && <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => { setHousekeepingRules(data.housekeeping_rules ?? []); setHousekeepingOpen(true) }}><Settings2 size={15} /> Housekeeping</button>}
                <button type="button" className={`entropy-button entropy-button-secondary entropy-button-sm${showArchived ? ' active' : ''}`} onClick={() => { setShowArchived((value) => !value); setSelectedReleaseIds(new Set()); setSelectedPromotionIds(new Set()) }}><Archive size={15} /> {showArchived ? 'Archived' : 'Active'}</button>
                <div className="release-traceability"><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!visibleReleases.length} aria-expanded={combinedTraceabilityMenu} onClick={() => setCombinedTraceabilityMenu((open) => !open)}>Traceability</button>{combinedTraceabilityMenu && <div className="release-traceability-menu" role="menu"><button type="button" role="menuitem" onClick={() => { setTraceabilityView('releases'); setTraceabilityOpen(true); setCombinedTraceabilityMenu(false) }}><Search size={15} /> Review report</button><button type="button" role="menuitem" onClick={() => { setCombinedTraceabilityMenu(false); exportCombinedTraceabilityExcel() }}><FileSpreadsheet size={15} /> Download Excel report</button><button type="button" role="menuitem" onClick={() => { setCombinedTraceabilityMenu(false); void copyCombinedTraceabilityReport() }}><Clipboard size={15} /> Copy for Outlook</button></div>}</div>
                {data?.permissions['releases.manage'] && <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={exportReleases} disabled={!data.items.length} title="Export release JSON"><Download size={15} /> Export</button>}
                {data?.permissions['releases.create'] && <label className="entropy-button entropy-button-secondary entropy-button-sm release-import-button" title="Import an Entropy release JSON export"><Upload size={15} /> Import<input type="file" accept=".json,application/json" disabled={busy} onChange={(event) => { void importReleases(event.currentTarget.files?.[0]); event.currentTarget.value = '' }} /></label>}
                {data?.permissions['releases.create'] && <button className="entropy-button entropy-button-primary entropy-button-sm" onClick={() => { setDraft({ ...blankRelease, workflow_name: data.workflows[0]?.name ?? '' }); setCreating(true) }}><Plus size={16} /> New release</button>}
            </div>
        </header>

        {!data ? <EntropyLoader label="Loading releases…" /> : <>
            <nav className="release-tabs" aria-label="Release views">
                <button className={tab === 'releases' ? 'active' : ''} onClick={() => setTab('releases')}>Releases <span>{visibleReleases.length}</span></button>
                <button className={tab === 'promotions' ? 'active' : ''} onClick={() => setTab('promotions')}>Promotions <span>{visiblePromotions.filter((item) => item.status === 'queued').length}</span></button>
                <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>Promotion history <span>{visiblePromotions.length}</span></button>
            </nav>
            <datalist id="release-environment-options">{data.environments.map((environment) => <option key={environment} value={environment} />)}</datalist>

            {tab === 'releases' && <>
                <div className="release-list-toolbar"><label className="release-search"><Search size={16} /><input value={releaseSearch} onChange={(event) => setReleaseSearch(event.target.value)} placeholder="Search releases by name, tag, environment…" aria-label="Search releases" /></label><select aria-label="Sort releases" value={releaseSort} onChange={(event) => setReleaseSort(event.target.value as typeof releaseSort)}><option value="newest">Newest first</option><option value="updated">Recently updated</option><option value="name">Name A–Z</option><option value="environment">Environment</option></select></div>
                {data.permissions['releases.manage'] && !showArchived && visibleReleases.length > 0 && <div className="release-bulk-toolbar"><label><input type="checkbox" checked={visibleReleases.every((item) => selectedReleaseIds.has(item.id))} onChange={(event) => setSelectedReleaseIds(event.target.checked ? new Set(visibleReleases.map((item) => item.id)) : new Set())} /> Select all {visibleReleases.length} releases</label><span>{selectedReleaseIds.size} selected</span><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!selectedReleaseIds.size || busy} onClick={() => void archiveSelected('release')}><Archive size={15} /> Archive selected</button><small>Archiving keeps all release data; it does not delete anything.</small></div>}
                {visibleReleases.length ? <div className="release-list">
                    {releasePages.pageItems.map((release) => <article className={`release-row${selectedId === release.id ? ' selected' : ''}`} key={release.id}>
                        {data.permissions['releases.manage'] && !showArchived && <label className="release-select-checkbox" aria-label={`Select release ${release.name}`}><input type="checkbox" checked={selectedReleaseIds.has(release.id)} onChange={() => toggleArchiveSelection(release.id, 'release')} /></label>}
                        <button className="release-main" onClick={() => setSelectedId(release.id)}>
                            <span className="release-title">{release.name}{release.version && <small>{release.version}</small>}</span>
                            <span className="release-subtitle"><WorkflowIcon size={14} /> {release.workflow_name}</span>
                        </button>
                        <span className={`release-env-chip${release.environment ? '' : ' is-empty'}`} title="Environment"><MapPin size={12} /> {release.environment || 'No environment'}</span>
                        <span className={`release-stage stage-${release.stage}`}>{readable(stages.find((stage) => stage.id === release.stage)?.label ?? release.stage)}</span>
                        <span className="release-task-count">{release.tasks.length} task{release.tasks.length === 1 ? '' : 's'}</span>
                        <span className={`release-run-state ${release.workflow_state ?? ''}`}>{release.workflow_state ? `Workflow ${readable(release.workflow_state)}` : ''}</span>
                        {data.permissions['releases.manage'] && data.permissions['workflows.execute'] && release.stage === 'workflow_queue' && (!release.workflow_job_id || ['failed', 'cancelled'].includes(release.workflow_state ?? '')) && <button className="entropy-button entropy-button-secondary entropy-button-sm" disabled={busy} onClick={() => void runWorkflow(release)}><Play size={14} /> {release.workflow_job_id ? 'Retry workflow' : 'Run workflow'}</button>}
                    </article>)}
                    <Pagination state={releasePages} noun="releases" />
                </div> : <div className="release-empty"><PackageCheck size={25} /><strong>{showArchived ? 'No archived releases' : 'No releases found'}</strong><span>{releaseSearch ? 'Try changing your search.' : 'Create a release and map it to a project workflow.'}</span></div>}
            </>}

            {tab === 'promotions' && <>
                {data.permissions['releases.promote'] && <section className="promotion-queue">
                    <div className="promotion-queue-heading"><div><h4>Create promotion</h4><p>Select completed releases, choose the target environment and the promotion workflow. Run the promotion from the queue when ready; the releases move to the target environment when it completes.</p></div><ArrowUpRight size={18} /></div>
                    <div className="promotion-controls"><span className="promotion-selection">{promotionReleaseIds.size} selected</span><button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setPromotionReleaseIds((current) => current.size === completed.length ? new Set() : new Set(completed.map((item) => item.id)))}>{promotionReleaseIds.size === completed.length && completed.length ? 'Clear selection' : 'Select all completed'}</button><input value={promotionNumber} onChange={(event) => setPromotionNumber(event.target.value)} placeholder="Promotion number (optional)" aria-label="Promotion number" /><input list="release-environment-options" aria-label="Target environment" placeholder="Target environment" value={targetEnvironment} onChange={(event) => setTargetEnvironment(event.target.value)} /><select aria-label="Promotion workflow" value={promotionWorkflow} onChange={(event) => setPromotionWorkflow(event.target.value)}><option value="">Promotion workflow…</option>{data.workflows.map((workflow) => <option key={workflow.name} value={workflow.name}>{workflow.name}</option>)}</select><button className="entropy-button entropy-button-primary entropy-button-sm" disabled={!promotionReleaseIds.size || !targetEnvironment.trim() || busy} onClick={() => void createPromotionRecord()}><Plus size={14} /> Create promotion</button></div>
                    <div className="promotion-environments"><MapPin size={14} /><span>Environments:</span>{data.environments.length ? data.environments.map((environment) => <span className="release-env-chip" key={environment}>{environment}</span>) : <small>None yet</small>}<input value={newEnvironment} onChange={(event) => setNewEnvironment(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void addEnvironment() }} placeholder="New environment" aria-label="New environment" maxLength={100} /><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!newEnvironment.trim()} onClick={() => void addEnvironment()}><Plus size={14} /> Add</button></div>
                    <div className="promotion-release-picker">{completed.map((release) => <label key={release.id}><input type="checkbox" checked={promotionReleaseIds.has(release.id)} onChange={() => togglePromotionRelease(release.id)} /><span><strong>{release.name}{release.version ? ` ${release.version}` : ''}</strong><small>{release.environment || 'No environment'} · {release.tasks.length} tasks</small></span></label>)}{!completed.length && <small>No completed releases are available to promote.</small>}</div>
                </section>}
                {queuedPromotions.length ? <div className="promotion-list">{queuedPages.pageItems.map((promotion) => <article key={promotion.id}>
                    <div><strong>{promotion.promotion_number} · {promotion.releases.length} release{promotion.releases.length === 1 ? '' : 's'} → {promotion.target_environment}</strong><span>Created by {promotion.created_by} · {new Date(promotion.created_at).toLocaleString()}</span></div><div className="promotion-release-names">{promotion.releases.map((release) => `${release.name}${release.version ? ` ${release.version}` : ''}`).join(', ')}</div><div className="promotion-run-controls"><select aria-label={`Promotion workflow for ${promotion.promotion_number}`} value={workflowFor(promotion)} onChange={(event) => { const value = event.target.value; setRunWorkflows((current) => ({ ...current, [promotion.id]: value })) }}><option value="">Choose promotion workflow</option>{data.workflows.map((workflow) => <option key={workflow.name} value={workflow.name}>{workflow.name}</option>)}</select><button type="button" className="entropy-button entropy-button-primary entropy-button-sm" disabled={!workflowFor(promotion) || busy || !data.permissions['workflows.execute']} title={data.permissions['workflows.execute'] ? undefined : 'You may not run workflows'} onClick={() => void runPromotion(promotion)}><Play size={14} /> Run promotion</button></div>
                </article>)}<Pagination state={queuedPages} noun="promotions" /></div> : <div className="release-empty"><ArrowUpRight size={25} /><strong>No queued promotions</strong><span>Select completed releases to create a promotion.</span></div>}
            </>}

            {tab === 'history' && <>
                {data.permissions['releases.manage'] && !showArchived && historyPromotions.length > 0 && <div className="release-bulk-toolbar"><label><input type="checkbox" checked={historyPromotions.every((item) => selectedPromotionIds.has(item.id))} onChange={(event) => setSelectedPromotionIds(event.target.checked ? new Set(historyPromotions.map((item) => item.id)) : new Set())} /> Select all {historyPromotions.length} promotion records</label><span>{selectedPromotionIds.size} selected</span><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!selectedPromotionIds.size || busy} onClick={() => void archiveSelected('promotion')}><Archive size={15} /> Archive selected</button><small>Archiving keeps all promotion history; it does not delete anything.</small></div>}
                {historyPromotions.length ? <div className="promotion-list">{historyPages.pageItems.map((promotion) => <article className="promotion-history-row" key={promotion.id}>
                {data.permissions['releases.manage'] && !showArchived && <label className="release-select-checkbox" aria-label={`Select promotion ${promotion.promotion_number}`}><input type="checkbox" checked={selectedPromotionIds.has(promotion.id)} onChange={() => toggleArchiveSelection(promotion.id, 'promotion')} /></label>}
                <div><strong>{promotion.promotion_number} · {promotion.releases.length} release{promotion.releases.length === 1 ? '' : 's'} → {promotion.target_environment}</strong><span>Promotion workflow: {promotion.workflow_name || 'Not chosen'}{promotion.workflow_job_id ? <> · <a href={`#/runs/${promotion.workflow_job_id}`}>run #{promotion.workflow_job_id}</a></> : null}</span></div><div className="promotion-release-names">{promotion.releases.map((release) => `${release.name}${release.version ? ` ${release.version}` : ''}`).join(', ')}</div><span className={`promotion-status status-${promotion.status}`}>{readable(promotion.workflow_state ?? promotion.status)}</span>
            </article>)}<Pagination state={historyPages} noun="promotions" /></div> : <div className="release-empty"><ArrowUpRight size={25} /><strong>No promotion history</strong><span>Completed and failed promotion runs will appear here.</span></div>}
            </>}
        </>}

        {creating && data && <ReleaseModalLayer onClose={() => setCreating(false)}><form className="release-dialog" onSubmit={(event) => void createRelease(event)}>
            <header><div><h3>Create release</h3><p>Map this release to a workflow in the active project.</p></div><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setCreating(false)} aria-label="Close"><X size={18} /></button></header>
            <label>Release name<input autoFocus value={draft.name} onChange={(event) => setReleaseField('name', event.target.value)} required maxLength={200} placeholder="e.g. Payments API" /></label>
            <div className="release-form-grid"><label>Version<input value={draft.version} onChange={(event) => setReleaseField('version', event.target.value)} placeholder="e.g. 2.8.0" /></label><label>Current environment<input list="release-environment-options" value={draft.environment} onChange={(event) => setReleaseField('environment', event.target.value)} placeholder="Choose or type an environment" /><small>New environment names are added to the shared Release Manager list when saved.</small></label></div>
            <label>Workflow<select required value={draft.workflow_name} onChange={(event) => setReleaseField('workflow_name', event.target.value)}><option value="">Choose workflow</option>{data.workflows.map((workflow) => <option key={workflow.name} value={workflow.name}>{workflow.name}</option>)}</select><small>Release workflows run from the workflow queue. Their variables include release_id, release_name, release_version, and release.</small></label>
            <label>Tags<input value={draft.tags} onChange={(event) => setReleaseField('tags', event.target.value)} placeholder="SIT, payments, urgent" /><small>Separate tags with commas.</small></label>
            {data.permissions['artifacts.read'] && <label>Link artifacts<select multiple value={draft.artifact_ids.map(String)} onChange={(event) => setDraft((current) => ({ ...current, artifact_ids: Array.from(event.target.selectedOptions, (option) => Number(option.value)) }))}>{artifacts.map((artifact) => <option key={artifact.id} value={artifact.id}>{artifact.name}</option>)}</select><small>Choose packages already registered in Artifacts. Use Ctrl or Command to select multiple.</small></label>}
            <label>Description<textarea rows={3} value={draft.description} onChange={(event) => setReleaseField('description', event.target.value)} maxLength={10000} /></label>
            {!data.workflows.length && <div className="release-form-note">Create a workflow in this project before adding a release.</div>}
            <footer><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setCreating(false)}>Cancel</button><button type="submit" className="entropy-button entropy-button-primary" disabled={busy || !draft.name.trim() || !draft.workflow_name}>{busy ? 'Creating…' : 'Create release'}</button></footer>
        </form></ReleaseModalLayer>}

        {housekeepingOpen && <ReleaseModalLayer onClose={() => setHousekeepingOpen(false)}><section className="release-dialog release-housekeeping-dialog">
            <header><div><h3>Release Manager housekeeping</h3><p>Archive older releases and promotion records by status and age. Rules are applied automatically when Release Manager loads.</p></div><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setHousekeepingOpen(false)} aria-label="Close"><X size={18} /></button></header>
            <div className="release-housekeeping-rules">{housekeepingRules.map((rule, index) => <div key={`${rule.entity}-${rule.older_than_days}-${index}`}><span><strong>{rule.entity === 'release' ? 'Releases' : 'Promotions'}</strong><small>{rule.statuses.length ? rule.statuses.map(readable).join(', ') : 'default completed states'} · older than {rule.older_than_days} days</small></span><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" aria-label="Remove rule" onClick={() => setHousekeepingRules((current) => current.filter((_, currentIndex) => currentIndex !== index))}><X size={15} /></button></div>)}{!housekeepingRules.length && <p>No archive rules configured.</p>}</div>
            <div className="release-housekeeping-add"><label>Record type<select value={housekeepingDraft.entity} onChange={(event) => setHousekeepingDraft((current) => ({ ...current, entity: event.target.value as HousekeepingRule['entity'], statuses: event.target.value === 'release' ? ['completed'] : ['completed', 'failed', 'cancelled'] }))}><option value="release">Release</option><option value="promotion">Promotion</option></select></label><label>Older than (days)<input type="number" min="1" max="36500" value={housekeepingDraft.older_than_days} onChange={(event) => setHousekeepingDraft((current) => ({ ...current, older_than_days: Number(event.target.value) }))} /></label><label>Statuses<select multiple value={housekeepingDraft.statuses} onChange={(event) => setHousekeepingDraft((current) => ({ ...current, statuses: Array.from(event.target.selectedOptions, (option) => option.value) }))}>{(housekeepingDraft.entity === 'release' ? stages.map((stage) => stage.id) : ['queued', 'completed', 'failed', 'cancelled']).map((status) => <option key={status} value={status}>{readable(status)}</option>)}</select><small>Leave empty to use completed states only.</small></label><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={addHousekeepingRule}><Plus size={14} /> Add rule</button></div>
            <footer><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setHousekeepingOpen(false)}>Cancel</button><button type="button" className="entropy-button entropy-button-secondary" disabled={busy} onClick={() => void saveHousekeeping(true)}><Archive size={15} /> Save and archive now</button><button type="button" className="entropy-button entropy-button-primary" disabled={busy} onClick={() => void saveHousekeeping()}>Save rules</button></footer>
        </section></ReleaseModalLayer>}

        {traceabilityOpen && <ReleaseModalLayer onClose={() => setTraceabilityOpen(false)}><section className="release-dialog release-traceability-dialog">
            <header><div><h3>Release traceability</h3><p>Review the releases and their tasks. Copying for Outlook takes both tables; the Excel report adds pivot summaries.</p></div><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setTraceabilityOpen(false)} aria-label="Close"><X size={18} /></button></header>
            <nav className="release-tabs" aria-label="Traceability report views"><button className={traceabilityView === 'releases' ? 'active' : ''} onClick={() => setTraceabilityView('releases')}>Releases</button><button className={traceabilityView === 'tasks' ? 'active' : ''} onClick={() => setTraceabilityView('tasks')}>Tasks</button></nav>
            <div className="release-traceability-table-wrap"><table className="release-traceability-table"><thead><tr>{(traceabilityView === 'releases' ? traceabilityRows().releaseRows[0] : traceabilityRows().taskRows[0]).map((heading) => <th key={heading}>{heading}</th>)}</tr></thead><tbody>{(traceabilityView === 'releases' ? traceabilityRows().releaseRows : traceabilityRows().taskRows).slice(1).map((row, index) => <tr key={`${index}-${row[0]}`}>{row.map((cell, cellIndex) => <td key={`${cellIndex}-${cell}`}>{cell}</td>)}</tr>)}</tbody></table></div>
            <footer><button type="button" className="entropy-button entropy-button-secondary" onClick={exportCombinedTraceabilityExcel}><FileSpreadsheet size={15} /> Download Excel</button><button type="button" className="entropy-button entropy-button-primary" onClick={() => void copyCombinedTraceabilityReport()}><Clipboard size={15} /> Copy releases and tasks for Outlook</button></footer>
        </section></ReleaseModalLayer>}

        {selected && data && <ReleaseModalLayer onClose={() => setSelectedId(null)}><section className="release-dialog release-detail">
            <header><div><span className="release-eyebrow">RELEASE #{selected.id}</span><h3>{selected.name}{selected.version ? ` · ${selected.version}` : ''}</h3><p>{selected.workflow_name} {selected.environment && `· ${selected.environment}`}</p></div><div className="release-detail-actions"><div className="release-traceability"><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" aria-expanded={traceabilityMenu} onClick={() => setTraceabilityMenu((open) => !open)}>Traceability</button>{traceabilityMenu && <div className="release-traceability-menu" role="menu"><button type="button" role="menuitem" onClick={exportTraceabilityExcel}><FileSpreadsheet size={15} /> Download Excel report</button><button type="button" role="menuitem" onClick={() => void copyTraceabilityReport()}><Clipboard size={15} /> Copy for Outlook</button></div>}</div><button className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setSelectedId(null)} aria-label="Close"><X size={18} /></button></div></header>
            <div className="release-detail-scroll">
                <div className="release-detail-summary"><span className={`release-stage stage-${selected.stage}`}>{readable(stages.find((stage) => stage.id === selected.stage)?.label ?? selected.stage)}</span><span>Created by <strong>{selected.created_by}</strong></span>{selected.workflow_job_id && <a href={`#/runs/${selected.workflow_job_id}`}>Workflow run #{selected.workflow_job_id} · {readable(selected.workflow_state ?? 'unknown')}</a>}</div>
                {selected.description && <p className="release-description">{selected.description}</p>}
                {selected.tags?.length > 0 && <div className="release-tag-list">{selected.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
                {selected.artifacts?.length > 0 && <section className="release-linked-artifacts"><h4>Linked artifacts</h4><ul>{selected.artifacts.map((artifact) => <li key={artifact.id}><strong>{artifact.name}</strong><small>{artifact.size_bytes.toLocaleString()} bytes</small></li>)}</ul></section>}
                <label className="release-stage-field">Environment
                    {data.permissions['releases.manage'] && !selected.archived_at && selected.stage !== 'completed' ? <span className="release-env-edit"><input list="release-environment-options" value={environmentDraft} onChange={(event) => setEnvironmentDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void saveEnvironment(selected) }} placeholder="Choose or type an environment" maxLength={100} /><button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={environmentDraft.trim() === selected.environment} onClick={() => void saveEnvironment(selected)}>Save</button></span> : <span className="release-env-chip"><MapPin size={12} /> {selected.environment || 'No environment'}</span>}
                    <small>{selected.stage === 'completed' ? 'Completed releases change environment through a promotion.' : 'New names are added to the environment list.'}</small>
                </label>
                {data.permissions['releases.manage'] && !selected.archived_at && <label className="release-stage-field">Stage<select value={selected.stage} onChange={(event) => void updateStage(selected, event.target.value as Stage)}>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.label}</option>)}</select><small>Mark Completed after every linked task is done. Completed releases enter the promotion queue.</small></label>}
                <section className="release-linked-tasks"><div className="release-section-heading"><div><h4>Linked tasks <span>{selected.tasks.length}</span></h4><p>Linked tasks are tagged to this release and remain in Tasks.</p></div>{data.permissions['tasks.create'] && <div className="release-task-actions"><button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setShowTaskForm((value) => !value)}><ListPlus size={15} /> Add task</button><label className="entropy-button entropy-button-secondary entropy-button-sm release-import-button" title='Upload JSON: [{"title":"Task title","description":"Details","remarks":"Notes","assignee":"username"}]'><FileJson2 size={15} /> Import JSON<input type="file" accept=".json,application/json" onChange={(event) => { void importTasks(event.target.files?.[0]); event.currentTarget.value = '' }} /></label></div>}</div>
                    {data.permissions['tasks.create'] && existingTasks.length > 0 && <div className="release-link-existing"><select aria-label="Select existing task" value={linkTaskId} onChange={(event) => setLinkTaskId(event.target.value)}><option value="">Link an existing task…</option>{existingTasks.map((task) => <option key={task.id} value={task.id}>{task.key ?? `#${task.id}`} · {task.title}</option>)}</select><button className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!linkTaskId} onClick={() => void linkExistingTask()}>Link task</button></div>}
                    {showTaskForm && <form className="release-task-form" onSubmit={(event) => void addTask(event)}><label>Title<input autoFocus value={taskDraft.title} onChange={(event) => setTaskField('title', event.target.value)} required /></label><label>Description<textarea rows={2} value={taskDraft.description} onChange={(event) => setTaskField('description', event.target.value)} /></label><label>Remarks<textarea rows={2} value={taskDraft.remarks} onChange={(event) => setTaskField('remarks', event.target.value)} /></label><label>Assign to<select value={taskDraft.assignee} onChange={(event) => setTaskField('assignee', event.target.value)}><option value="">Unassigned</option>{projectMembers.map((member) => <option key={member.username} value={member.username}>{member.full_name ? `${member.full_name} (${member.username})` : member.username}</option>)}</select></label><button className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy}><Plus size={14} /> Create linked task</button></form>}
                    {selected.tasks.length ? <ul>{selected.tasks.map((task) => <li key={task.id}><span><strong>{task.key ?? `#${task.id}`} · {task.title}</strong><small>{taskStatus(task.status)}{task.assignee ? ` · ${task.assignee}` : ''}{task.comments?.length ? ` · ${task.comments.length} comment${task.comments.length === 1 ? '' : 's'}: ${task.comments.map((comment) => comment.body).join(' | ')}` : ''}</small></span>{!selected.archived_at && <button className="entropy-button entropy-button-ghost entropy-button-sm" title="Unlink task" onClick={() => void unlinkTask(task.id)}><X size={15} /></button>}</li>)}</ul> : <div className="release-task-empty">No tasks linked. Add tasks manually, import JSON, or link existing project tasks.</div>}
                </section>
            </div>
        </section></ReleaseModalLayer>}
    </div>
}
