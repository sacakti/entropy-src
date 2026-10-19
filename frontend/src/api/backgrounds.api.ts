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

/** Zip of every background the user uploaded; built-ins are excluded. */
export const BACKGROUNDS_ARCHIVE_URL = '/api/backgrounds/archive'

/** Delete every background the user uploaded; built-ins are kept. */
export async function deleteAllBackgrounds(): Promise<{ deleted: number; message: string }> {
    return apiRequest<{ deleted: number; message: string }>('/api/backgrounds', {
        method: 'DELETE',
    })
}

export function isVideoBackground(background: Pick<BackgroundImage, 'mime_type'>): boolean {
    return background.mime_type.startsWith('video/')
}

/** MIME types the upload endpoint accepts. */
export const BACKGROUND_UPLOAD_TYPES = [
    'image/png',
    'image/jpeg',
    'image/webp',
    'video/mp4',
    'video/webm',
]
