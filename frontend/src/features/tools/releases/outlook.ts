import type { Promotion, Release, ReleaseTask } from './ReleaseManager'

const STAGES: Record<string, string> = {
    workflow_queue: 'Workflow queue',
    workflow_done: 'Workflow done',
    task_queue: 'Task queue',
    completed: 'Completed',
}
const TASK_STATUSES: Record<string, string> = { todo: 'Open', in_progress: 'In progress', done: 'Closed', reopened: 'Reopened' }

const readable = (value: string) => value.replaceAll('_', ' ')
const escape = (value: string) =>
    value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')
const day = (value?: string | null) => (value ?? '').replace('T', ' ').slice(0, 16)

export const releaseLabel = (release: Release) => (release.version ? `${release.name} ${release.version}` : release.name)
export const taskStatus = (status: string) => TASK_STATUSES[status] ?? readable(status)
export const stageLabel = (stage: string) => STAGES[stage] ?? readable(stage)

const taskKey = (task: ReleaseTask) => task.key ?? `#${task.id}`
const assigned = (task: ReleaseTask) =>
    task.assignee ? [task.assigned_by && `by ${task.assigned_by}`, task.assigned_at && `on ${day(task.assigned_at)}`].filter(Boolean).join(' ') || 'Yes' : ''
const comments = (task: ReleaseTask) => (task.comments ?? []).map((item) => `${item.author} (${day(item.created_at)}): ${item.body}`)
const workflowRun = (release: Release) =>
    release.workflow_job_id ? `#${release.workflow_job_id} (${readable(release.workflow_state ?? 'unknown')})` : 'Not started'
const promotionsOf = (release: Release, promotions: Promotion[]) =>
    promotions
        .filter((promotion) => promotion.releases.some((item) => item.id === release.id))
        .map((promotion) => `${promotion.promotion_number} → ${promotion.target_environment} (${readable(promotion.workflow_state ?? promotion.status)})`)

export const RELEASE_HEADER = ['Release ID', 'Release', 'Environment', 'Stage', 'Workflow', 'Workflow run', 'Tasks closed', 'Promotions']
export const TASK_HEADER = ['ID', 'Name', 'Description', 'Status', 'Release', 'Assignee', 'Assigned', 'Comments', 'Attachments', 'External ref no', 'Remarks']

export function releaseRows(releases: Release[], promotions: Promotion[]): string[][] {
    return [
        RELEASE_HEADER,
        ...releases.map((release) => [
            String(release.id),
            releaseLabel(release),
            release.environment || '—',
            stageLabel(release.stage),
            release.workflow_name,
            workflowRun(release),
            `${release.tasks.filter((task) => task.status === 'done').length}/${release.tasks.length}`,
            promotionsOf(release, promotions).join('; ') || '—',
        ]),
    ]
}

export function taskRows(releases: Release[]): string[][] {
    return [
        TASK_HEADER,
        ...releases.flatMap((release) =>
            release.tasks.map((task) => [
                taskKey(task),
                task.title,
                task.description ?? '',
                taskStatus(task.status),
                releaseLabel(release),
                task.assignee ?? 'Unassigned',
                assigned(task),
                comments(task).join('\n'),
                task.attachment_count ? 'Yes' : 'No',
                task.external_ref ?? '',
                task.remarks ?? '',
            ]),
        ),
    ]
}

// Outlook (Word engine) keeps inline styles and table attributes, not classes.
const FONT = "font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:11pt;color:#1d2433"
const CELL = 'border:1px solid #bfbfbf;padding:5px 8px;vertical-align:top;text-align:left'
const HEAD = `${CELL};background:#1f4e78;color:#ffffff;font-weight:bold`

function table(rows: string[][]): string {
    const [header, ...body] = rows
    const cell = (value: string) => escape(value || '—').replaceAll('\n', '<br>')
    return (
        `<table cellpadding="0" cellspacing="0" border="1" style="border-collapse:collapse;${FONT};margin:4px 0 14px">` +
        `<thead><tr>${header.map((value) => `<th bgcolor="#1f4e78" style="${HEAD}">${escape(value)}</th>`).join('')}</tr></thead>` +
        `<tbody>${body.length ? body.map((row) => `<tr>${row.map((value) => `<td style="${CELL}">${cell(value)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${header.length}" style="${CELL}">None</td></tr>`}</tbody></table>`
    )
}

function details(release: Release, promotions: Promotion[]): string {
    const rows: [string, string][] = [
        ['Release', releaseLabel(release)],
        ['Environment', release.environment || '—'],
        ['Stage', stageLabel(release.stage)],
        ['Workflow', `${release.workflow_name} · run ${workflowRun(release)}`],
        ['Tasks closed', `${release.tasks.filter((task) => task.status === 'done').length} of ${release.tasks.length}`],
        ['Promotions', promotionsOf(release, promotions).join('; ') || '—'],
        ['Description', release.description || '—'],
    ]
    return (
        `<table cellpadding="0" cellspacing="0" border="1" style="border-collapse:collapse;${FONT};margin:4px 0 14px">` +
        rows.map(([label, value]) => `<tr><th bgcolor="#ddebf7" style="${CELL};background:#ddebf7;width:140px">${escape(label)}</th><td style="${CELL}">${escape(value).replaceAll('\n', '<br>')}</td></tr>`).join('') +
        '</table>'
    )
}

const plainTable = (rows: string[][]) => rows.map((row) => row.map((value) => value.replaceAll('\n', ' / ')).join('\t')).join('\n')

/** Releases and their tasks as Outlook-ready HTML, with a tab-separated plain-text twin. */
export function outlookReport(heading: string, releases: Release[], promotions: Promotion[]): { html: string; plain: string } {
    const tasks = taskRows(releases)
    const title = (text: string, size: number) => `<p style="${FONT};font-size:${size}pt;font-weight:bold;color:#1f4e78;margin:10px 0 4px">${escape(text)}</p>`
    const intro = releases.length === 1 ? details(releases[0], promotions) : table(releaseRows(releases, promotions))
    const html =
        `<div style="${FONT}">${title(heading, 14)}` +
        `<p style="${FONT};color:#595959;margin:0 0 8px">Generated ${escape(new Date().toLocaleString())} from Entropy Release Manager.</p>` +
        (releases.length === 1 ? '' : title(`Releases (${releases.length})`, 12)) +
        intro +
        title(`Tasks (${tasks.length - 1})`, 12) +
        table(tasks) +
        '</div>'
    const plain = [
        heading,
        '',
        releases.length === 1
            ? releaseRows(releases, promotions).slice(1).map((row) => RELEASE_HEADER.map((label, index) => `${label}: ${row[index]}`).join('\n'))[0]
            : plainTable(releaseRows(releases, promotions)),
        '',
        `Tasks (${tasks.length - 1})`,
        plainTable(tasks),
    ].join('\n')
    return { html, plain }
}

/**
 * Put HTML and plain text on the clipboard. The copy-event route works on
 * plain http and in every browser; the async Clipboard API is the fallback.
 */
export async function copyRich(html: string, plain: string): Promise<void> {
    let copied = false
    const listener = (event: ClipboardEvent) => {
        if (!event.clipboardData) return
        event.clipboardData.setData('text/html', `<html><body>${html}</body></html>`)
        event.clipboardData.setData('text/plain', plain)
        event.preventDefault()
        copied = true
    }
    document.addEventListener('copy', listener)
    try {
        document.execCommand('copy')
    } finally {
        document.removeEventListener('copy', listener)
    }
    if (copied) return
    if (navigator.clipboard && typeof ClipboardItem !== 'undefined') {
        await navigator.clipboard.write([
            new ClipboardItem({
                'text/html': new Blob([html], { type: 'text/html' }),
                'text/plain': new Blob([plain], { type: 'text/plain' }),
            }),
        ])
        return
    }
    throw new Error('The browser did not allow copying. Use the Excel report instead.')
}
