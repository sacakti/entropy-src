import { currentProject } from './project'

const PROJECT_HEADER = 'X-Entropy-Project'

interface ApiErrorResponse {
    detail?: unknown
    message?: string
}

/** Error thrown for non-2xx responses; `detail` keeps structured payloads. */
export class ApiError extends Error {
    readonly status: number
    readonly detail: unknown

    constructor(message: string, status: number, detail: unknown) {
        super(message)
        this.name = 'ApiError'
        this.status = status
        this.detail = detail
    }
}

async function toApiError(
    response: Response,
): Promise<ApiError> {
    const body = await response.text()
    const fallback = `Request failed (${response.status}).`

    if (!body) {
        return new ApiError(fallback, response.status, null)
    }

    try {
        const data = JSON.parse(body) as ApiErrorResponse
        const detail = data.detail
        const message =
            typeof detail === 'string'
                ? detail
                : typeof (detail as { message?: unknown } | null)?.message === 'string'
                  ? (detail as { message: string }).message
                  : data.message ?? fallback

        // FastAPI's bare "Not Found" means the route itself is missing: the
        // server is running code older than this UI.
        if (response.status === 404 && detail === 'Not Found') {
            return new ApiError(
                `The Entropy web server does not provide ${new URL(response.url).pathname}. ` +
                    'It is running older code than this page; restart it from the updated ' +
                    'checkout (python -m core.web).',
                response.status,
                detail,
            )
        }

        return new ApiError(message, response.status, detail)
    } catch {
        return new ApiError(body, response.status, body)
    }
}

/** Dispatched on `window` when the server reports the session has ended. */
export const SESSION_EXPIRED_EVENT = 'entropy:session-expired'

async function getCsrfToken(): Promise<string> {
    const response = await fetch('/api/auth/csrf', {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
    })

    if (!response.ok) {
        throw new Error('Unable to obtain a CSRF token.')
    }

    const data: { csrf_token: string } = await response.json()
    return data.csrf_token
}

export async function apiRequest<T>(
    url: string,
    init: RequestInit = {},
): Promise<T> {
    const method = (init.method ?? 'GET').toUpperCase()
    const headers = new Headers(init.headers)

    if (method !== 'GET' && method !== 'HEAD') {
        headers.set('X-CSRF-Token', await getCsrfToken())
    }
    const project = currentProject()
    if (project && !headers.has(PROJECT_HEADER)) headers.set(PROJECT_HEADER, project)

    const response = await fetch(url, {
        ...init,
        method,
        headers,
        credentials: 'same-origin',
        cache: 'no-store',
    })

    if (!response.ok) {
        if (response.status === 401 && !url.startsWith('/api/auth/')) {
            window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
        }

        throw await toApiError(response)
    }

    // DELETE endpoints may return 204 No Content.
    if (
        response.status === 204 ||
        method === 'HEAD'
    ) {
        return undefined as T
    }

    // Preserve support for successful JSON responses.
    return response.json() as Promise<T>
}

/** POST JSON and save the binary response (an export archive) as a file. */
export async function downloadFile(
    url: string,
    body: unknown,
    filename: string,
): Promise<void> {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': await getCsrfToken(),
            ...(currentProject() ? { [PROJECT_HEADER]: currentProject() as string } : {}),
        },
        body: JSON.stringify(body),
        credentials: 'same-origin',
        cache: 'no-store',
    })

    if (!response.ok) {
        throw await toApiError(response)
    }

    const link = document.createElement('a')
    link.href = URL.createObjectURL(await response.blob())
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    // Revoke after the browser has started the download.
    setTimeout(() => URL.revokeObjectURL(link.href), 10_000)
}
