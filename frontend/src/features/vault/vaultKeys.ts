import { vaultApi } from '../../api/vault.api'

/** Every `namespace/key` the current user may read; empty without vault access. */
export async function loadVaultKeys(): Promise<string[]> {
    try {
        const { items } = await vaultApi.listNamespaces()
        const entries = await Promise.all(
            items.map(async (namespace) => {
                try {
                    const result = await vaultApi.listEntries(namespace.name)
                    return result.items.map((entry) => `${namespace.name}/${entry.key}`)
                } catch {
                    return []
                }
            }),
        )
        return entries.flat().sort()
    } catch {
        return []
    }
}

/** The reference a workflow or run argument uses for a vault entry. */
export const vaultReference = (key: string) => `\${entv:${key}}`
