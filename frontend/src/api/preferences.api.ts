import { apiRequest } from '../services/api'

export type Theme = 'dark' | 'light'
export type BackgroundFit = 'cover' | 'contain' | 'fill'

export interface UserPreferences {
    theme: Theme
    accent_color: string
    background_image_id: number | null
    background_fit: BackgroundFit
    background_opacity: number
}

export async function getPreferences(): Promise<UserPreferences> {
    return apiRequest<UserPreferences>('/api/preferences')
}

export async function updatePreferences(
    preferences: UserPreferences,
): Promise<UserPreferences> {
    return apiRequest<UserPreferences>('/api/preferences', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(preferences),
    })
}
