interface ApiErrorResponse {
    detail?: string
    message?: string
}

async function getErrorMessage(
    response: Response,
): Promise<string> {
    const body = await response.text()

    if (!body) {
        return `Request failed (${response.status}).`
    }

    try {
        const data = JSON.parse(body) as ApiErrorResponse

        return (
            data.detail ??
            data.message ??
            `Request failed (${response.status}).`
        )
    } catch {
        return body
    }
}

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

    const response = await fetch(url, {
        ...init,
        method,
        headers,
        credentials: 'same-origin',
        cache: 'no-store',
    })

    if (!response.ok) {
        throw new Error(await getErrorMessage(response))
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
