import { apiRequest } from "../services/api"

export type VaultVisibility = "private" | "shared"

export type VaultValueType =
    | "string"
    | "number"
    | "boolean"
    | "array"
    | "object"
    | "json"

export type VaultAccess = "read" | "write" | "admin"

export interface VaultNamespace {
    id: number
    name: string
    owner_user_id: number
    visibility: VaultVisibility
    created_at: string | null
    updated_at: string | null
}

export interface VaultEntry {
    id: number
    key: string
    type: VaultValueType
    sensitive: boolean
    created_at: string | null
    updated_at: string | null
}

export interface VaultEntryWithValue extends VaultEntry {
    value: unknown
}

export interface VaultAccessAssignment {
    id: number
    namespace_id: number
    user_id: number
    /** Absent on servers older than the user-suggestion API. */
    username?: string | null
    full_name?: string | null
    access: VaultAccess
    created_at: string | null
}

export interface VaultUserSuggestion {
    id: number
    username: string
    full_name: string | null
}

interface CreateNamespaceRequest {
    name: string
    visibility: VaultVisibility
}

interface UpdateNamespaceRequest {
    name?: string
    visibility?: VaultVisibility
}

interface CreateEntryRequest {
    key: string
    value: unknown
    type: VaultValueType
    sensitive: boolean
}

interface UpdateEntryRequest {
    value: unknown
    type: VaultValueType
    sensitive: boolean
}

interface GrantAccessRequest {
    username: string
    access: VaultAccess
}

/**
 * API response wrappers returned by the backend.
 */
export interface VaultNamespacesResponse {
    items: VaultNamespace[]
}

export interface VaultEntriesResponse {
    items: VaultEntry[]
}

export interface VaultAccessResponse {
    items: VaultAccessAssignment[]
}

export interface VaultNamespaceResponse {
    namespace: VaultNamespace
}

export interface VaultEntryResponse {
    entry: VaultEntry
}

export interface VaultEntryWithValueResponse {
    entry: VaultEntryWithValue
}

const BASE_URL = "/api/vault"

export const vaultApi = {
    listNamespaces(): Promise<VaultNamespacesResponse> {
        return apiRequest<VaultNamespacesResponse>(
            `${BASE_URL}/namespaces`,
            {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
            },
        )
    },

    createNamespace(
        payload: CreateNamespaceRequest,
    ): Promise<VaultNamespaceResponse> {
        return apiRequest<VaultNamespaceResponse>(
            `${BASE_URL}/namespaces`,
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            },
        )
    },

    updateNamespace(
        namespaceName: string,
        payload: UpdateNamespaceRequest,
    ): Promise<VaultNamespaceResponse> {
        return apiRequest<VaultNamespaceResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}`,
            {
                method: "PATCH",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            },
        )
    },

    deleteNamespace(namespaceName: string): Promise<void> {
        return apiRequest<void>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}`,
            {
                method: "DELETE",
                credentials: "same-origin",
            },
        )
    },

    listEntries(
        namespaceName: string,
    ): Promise<VaultEntriesResponse> {
        return apiRequest<VaultEntriesResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/entries`,
            {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
            },
        )
    },

    createEntry(
        namespaceName: string,
        payload: CreateEntryRequest,
    ): Promise<VaultEntryResponse> {
        return apiRequest<VaultEntryResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/entries`,
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            },
        )
    },

    updateEntry(
        namespaceName: string,
        key: string,
        payload: UpdateEntryRequest,
    ): Promise<VaultEntryResponse> {
        return apiRequest<VaultEntryResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/entries/${encodeURIComponent(key)}`,
            {
                method: "PUT",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            },
        )
    },

    revealEntry(
        namespaceName: string,
        key: string,
    ): Promise<VaultEntryWithValueResponse> {
        return apiRequest<VaultEntryWithValueResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/entries/${encodeURIComponent(key)}/reveal`,
            {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
            },
        )
    },

    deleteEntry(
        namespaceName: string,
        key: string,
    ): Promise<void> {
        return apiRequest<void>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/entries/${encodeURIComponent(key)}`,
            {
                method: "DELETE",
                credentials: "same-origin",
            },
        )
    },

    listAccess(
        namespaceName: string,
    ): Promise<VaultAccessResponse> {
        return apiRequest<VaultAccessResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/access`,
            {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
            },
        )
    },

    grantAccess(
        namespaceName: string,
        payload: GrantAccessRequest,
    ): Promise<void> {
        return apiRequest<void>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/access`,
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            },
        )
    },

    revokeAccess(
        namespaceName: string,
        username: string,
    ): Promise<void> {
        return apiRequest<void>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/access/${encodeURIComponent(username)}`,
            {
                method: "DELETE",
                credentials: "same-origin",
            },
        )
    },

    suggestUsers(query: string): Promise<{ items: VaultUserSuggestion[] }> {
        return apiRequest<{ items: VaultUserSuggestion[] }>(
            `${BASE_URL}/users?${new URLSearchParams({ q: query }).toString()}`,
        )
    },
}
