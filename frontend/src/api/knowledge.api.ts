import { apiRequest, downloadUrl } from '../services/api'
import { currentProject } from '../services/project'

/** A file kept with an entry, shown in place when the entry's text names it. */
export interface KnowledgeAttachment {
    id: number
    entry_id: number
    filename: string
    content_type: string | null
    size_bytes: number
    uploaded_by: string
    created_at: string
}

/** One entry of a project's knowledge base, as listed (no body, an excerpt instead). */
export interface KnowledgeSummary {
    id: number
    project_id: number
    /** What was done. */
    title: string
    /** Where: an environment, a server, a system. */
    location: string
    /** When: a date, and a time ("HH:MM") if given. */
    happened_on: string
    happened_time: string | null
    /** Who took part: user names of members, or names of others. */
    people: string[]
    tags: string[]
    reference: string
    /** 1 when written, one more with each save that changes it. */
    version: number
    excerpt: string
    attachment_count: number
    created_by: string
    created_at: string
    updated_by: string
    updated_at: string
}

/** An entry in full. Its body is how it was done, in the task description format. */
export interface KnowledgeEntry extends Omit<KnowledgeSummary, 'excerpt' | 'attachment_count'> {
    body: string
    attachments: KnowledgeAttachment[]
    /** Earlier versions, newest first: who wrote each and when. */
    revisions: { id: number; version: number | null; edited_by: string; edited_at: string }[]
}

export interface KnowledgeRevision {
    id: number
    entry_id: number
    version: number | null
    edited_by: string
    edited_at: string
    title: string
    body: string
    location: string
    happened_on: string
    happened_time: string | null
    people: string[]
    tags: string[]
    reference: string
}

export type KnowledgeExportFormat = 'pdf' | 'html' | 'docx'

export interface KnowledgeMember {
    id: number
    username: string
    full_name: string | null
}

export interface KnowledgeList {
    items: KnowledgeSummary[]
    facets: { tags: string[]; locations: string[]; people: string[] }
    members: KnowledgeMember[]
    username: string
    permissions: { 'knowledge.write': boolean; 'knowledge.delete': boolean }
}

export interface KnowledgeFilters {
    q?: string
    tag?: string
    location?: string
    person?: string
    start?: string
    end?: string
}

export type KnowledgeValues = Partial<
    Pick<KnowledgeEntry, 'title' | 'body' | 'location' | 'happened_on' | 'happened_time' | 'people' | 'tags' | 'reference'>
>

const json = (method: string, body: unknown): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
})

export const knowledgeApi = {
    list(filters: KnowledgeFilters = {}): Promise<KnowledgeList> {
        const query = new URLSearchParams()
        Object.entries(filters).forEach(([key, value]) => {
            if (value) query.set(key, value)
        })
        const text = query.toString()
        return apiRequest(`/api/knowledge${text ? `?${text}` : ''}`)
    },
    get: (id: number) => apiRequest<KnowledgeEntry>(`/api/knowledge/${id}`),
    create: (values: KnowledgeValues) => apiRequest<KnowledgeEntry>('/api/knowledge', json('POST', values)),
    update: (id: number, values: KnowledgeValues) => apiRequest<KnowledgeEntry>(`/api/knowledge/${id}`, json('PATCH', values)),
    remove: (id: number) => apiRequest<void>(`/api/knowledge/${id}`, { method: 'DELETE' }),
    revision: (id: number, revisionId: number) =>
        apiRequest<KnowledgeRevision>(`/api/knowledge/${id}/revisions/${revisionId}`),
    attach(id: number, files: File[]): Promise<{ entry: KnowledgeEntry; added: KnowledgeAttachment[] }> {
        const form = new FormData()
        files.forEach((file) => form.append('files', file))
        return apiRequest(`/api/knowledge/${id}/attachments`, { method: 'POST', body: form })
    },
    detach: (id: number, attachmentId: number) =>
        apiRequest<void>(`/api/knowledge/${id}/attachments/${attachmentId}`, { method: 'DELETE' }),
    restore: (id: number, revisionId: number) =>
        apiRequest<KnowledgeEntry>(`/api/knowledge/${id}/revisions/${revisionId}/restore`, { method: 'POST' }),
    /** Download the entry, or one of its earlier versions, as a file. */
    export(id: number, format: KnowledgeExportFormat, fileName: string, revisionId?: number): Promise<void> {
        const query = new URLSearchParams({ format })
        if (revisionId !== undefined) query.set('revision', String(revisionId))
        return downloadUrl(`/api/knowledge/${id}/export?${query.toString()}`, fileName)
    },
    /** A new entry from a Word (.docx) or Markdown (.md) file. */
    importFile(file: File): Promise<KnowledgeEntry> {
        const form = new FormData()
        form.append('file', file)
        return apiRequest('/api/knowledge/import', { method: 'POST', body: form })
    },
    attachmentUrl(id: number, attachmentId: number): string {
        // A plain link (an <img>, a new tab) sends no project header: name it in the URL.
        const project = currentProject()
        return `/api/knowledge/${id}/attachments/${attachmentId}${project ? `?project=${encodeURIComponent(project)}` : ''}`
    },
}
