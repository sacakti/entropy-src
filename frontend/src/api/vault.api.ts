import { apiRequest, PROJECT_HEADER } from "../services/api"
import { currentProject } from "../services/project"

export type VaultValueType =
    | "string"
    | "number"
    | "boolean"
    | "array"
    | "object"
    | "json"
    // A file (certificate, keystore, key ...); uploaded and downloaded, not typed.
    | "file"

/** A namespace belongs to one project; access comes from the caller's project role. */
export interface VaultNamespace {
    id: number
    name: string
    project_id: number
    owner_user_id: number | null
    created_at: string | null
    updated_at: string | null
}

/** The caller's Vault permissions in the current project (same for every namespace). */
export interface VaultPermissions {
    namespace_read: boolean
    reveal: boolean
    add: boolean
    modify: boolean
    delete: boolean
    namespace_create: boolean
    namespace_modify: boolean
    namespace_delete: boolean
}

export interface VaultFileInfo {
    filename: string
    content_type: string
    size: number
}

export interface VaultEntry {
    id: number
    key: string
    type: VaultValueType
    sensitive: boolean
    created_at: string | null
    updated_at: string | null
    /** For file entries: the file's name, type and size (never its content). */
    file?: VaultFileInfo
}

export interface VaultEntryWithValue extends VaultEntry {
    value: unknown
}

interface CreateNamespaceRequest {
    name: string
}

interface UpdateNamespaceRequest {
    name: string
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

/**
 * API response wrappers returned by the backend.
 */
export interface VaultNamespacesResponse {
    /** Empty when the caller cannot read Vault namespaces in this project. */
    items: VaultNamespace[]
    permissions: VaultPermissions
}

export interface VaultEntriesResponse {
    items: VaultEntry[]
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

    /** Keep a file in the vault; `replace` overwrites the file under `key`. */
    uploadFile(
        namespaceName: string,
        key: string,
        file: File,
        sensitive: boolean,
        replace: boolean,
    ): Promise<VaultEntryResponse> {
        const body = new FormData()
        body.append("key", key)
        body.append("file", file)
        body.append("sensitive", String(sensitive))
        body.append("replace", String(replace))
        return apiRequest<VaultEntryResponse>(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/files`,
            { method: "POST", body },
        )
    },

    /** Download a file entry under its original name. */
    async downloadFile(namespaceName: string, key: string, filename: string): Promise<void> {
        const project = currentProject()
        const response = await fetch(
            `${BASE_URL}/namespaces/${encodeURIComponent(namespaceName)}/entries/${encodeURIComponent(key)}/download`,
            {
                credentials: "same-origin",
                cache: "no-store",
                headers: project ? { [PROJECT_HEADER]: project } : {},
            },
        )
        if (!response.ok) {
            const data = await response.json().catch(() => null)
            throw new Error(data?.detail ?? "Unable to download the file.")
        }
        const link = document.createElement("a")
        link.href = URL.createObjectURL(await response.blob())
        link.download = filename
        document.body.appendChild(link)
        link.click()
        link.remove()
        setTimeout(() => URL.revokeObjectURL(link.href), 10_000)
    },
}
