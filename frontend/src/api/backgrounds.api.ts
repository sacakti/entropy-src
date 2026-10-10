import { apiRequest } from '../services/api'

export interface BackgroundImage {
    id: number
    name: string
    mime_type: string
    size_bytes: number
    source: 'builtin' | 'upload'
    url: string
}

export async function getBackgrounds(): Promise<BackgroundImage[]> {
    return apiRequest<BackgroundImage[]>('/api/backgrounds')
}

export async function uploadBackground(file: File): Promise<void> {
    const formData = new FormData()
    formData.append('file', file)

    await apiRequest<unknown>('/api/backgrounds', {
        method: 'POST',
        body: formData,
    })
}

export async function deleteBackground(
    backgroundId: number,
): Promise<{ message: string }> {
    return apiRequest<{ message: string }>(
        `/api/backgrounds/${backgroundId}`,
        { method: 'DELETE' },
    )
}
