import { apiRequest } from "../services/api"

export interface ApplicationVersion {
    name: string
    version: string
}

export async function getApplicationVersion(): Promise<ApplicationVersion> {
    return apiRequest<ApplicationVersion>('/api/version', {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
    })
}
