

import {

    useCallback,

    useEffect,


    useRef,

    useState,

    type FormEvent,

} from 'react'

import {
    Eye,
    EyeOff,
    KeyRound,
    Plus,
    Shield,
    Trash2,
    Pencil,
    X,
    ChevronDown,
    LockKeyhole,
    FileJson,
    FileKey2,
    Download,
    Upload,
} from 'lucide-react'



import { vaultApi } from '../../api/vault.api'

import type {

    VaultAccess,

    VaultAccessAssignment,

    VaultEntry,

    VaultEntryWithValue,

    VaultNamespace,

    VaultValueType,

    VaultVisibility,

} from '../../api/vault.api'

import UserSuggestInput from './UserSuggestInput'
import VaultFileDialog from './VaultFileDialog'
import { VaultExportDialog, VaultImportDialog } from '../transfer/TransferDialogs'
import { missingPermission } from '../administration/permissionReason'
import { usePermissions } from '../administration/usePermissions'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import PickerDialog from '../../components/layout/PickerDialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Editor from '@monaco-editor/react'
import { useMonacoTheme } from '../tools/monacoTools'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'



type Tab = 'secrets' | 'access'

type ModalType = 'namespace' | 'entry' | 'detail' | null



interface EntryForm {

    key: string

    value: string

    type: VaultValueType

    sensitive: boolean

}



const emptyEntry: EntryForm = {

    key: '',

    value: '',

    type: 'string',

    sensitive: true,

}



const valueTypes: VaultValueType[] = [

    'string',

    'number',

    'boolean',

    'array',

    'json',

]



function getErrorMessage(error: unknown): string {

    if (error instanceof Error) {

        return error.message

    }



    return 'An unexpected error occurred.'

}



function formatValue(value: unknown): string {

    if (typeof value === 'string') {

        return value

    }



    try {

        return JSON.stringify(value, null, 2)

    } catch {

        return String(value)

    }

}



function previewValue(value: string, maxLength = 72): string {

    const normalized = value.replace(/\s+/g, ' ').trim()



    if (normalized.length <= maxLength) {

        return normalized

    }



    return `${normalized.slice(0, maxLength).trimEnd()}…`

}



function fileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isStructuredType(type: VaultValueType): boolean {

    return type === 'array' || type === 'object' || type === 'json'

}

function serializeVaultValue(value: string, type: VaultValueType): unknown {
    if (type === 'string') return value

    let parsed: unknown
    try {
        parsed = JSON.parse(value)
    } catch {
        if (type === 'number') {
            throw new Error('Expected a number. Enter one finite number, such as 42 or 3.14.')
        }
        throw new Error('Enter valid JSON syntax.')
    }
    if (type === 'number' && (typeof parsed !== 'number' || !Number.isFinite(parsed))) {
        throw new Error('Enter a finite JSON number, such as 42 or 3.14.')
    }
    if (type === 'boolean' && typeof parsed !== 'boolean') {
        throw new Error('Enter true or false.')
    }
    if (type === 'array' && !Array.isArray(parsed)) {
        throw new Error('Enter a JSON array, such as [1, 2].')
    }
    if (type === 'object' && (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object')) {
        throw new Error('Enter a JSON object, such as {"key":"value"}.')
    }

    return parsed
}

function vaultValueError(value: string, type: VaultValueType): string | null {
    if (!value || type === 'string') return null
    try {
        serializeVaultValue(value, type)
        return null
    } catch (cause) {
        return cause instanceof Error ? cause.message : 'Enter a valid value for the selected type.'
    }
}



export default function Vault() {

    const { notify, modal } = useFeedback()

    const monacoTheme = useMonacoTheme()

    const permissions = usePermissions()



    const [namespaces, setNamespaces] = useState<VaultNamespace[]>([])

    const [selectedNamespace, setSelectedNamespace] = useState('')

    const [portable, setPortable] = useState<'export' | 'import' | null>(null)

    // Upload a new file entry ('') or replace the file of an entry (its key).
    const [fileDialog, setFileDialog] = useState<string | null>(null)

    const [entries, setEntries] = useState<VaultEntry[]>([])

    const [accessAssignments, setAccessAssignments] = useState<

        VaultAccessAssignment[]

    >([])



    const [activeTab, setActiveTab] = useState<Tab>('secrets')

    // A namespace can open straight away; a secret waits for namespaces to load.
    const [modalType, setModalType] = useState<ModalType>(() =>
        consumeCreateIntent('vault-namespace') ? 'namespace' : null,
    )

    const pendingEntryRef = useRef(consumeCreateIntent('vault-entry'))

    const selectedAccess =

        namespaces.find((namespace) => namespace.name === selectedNamespace)?.access ?? null

    const isNamespaceAdmin = selectedAccess === 'admin'

    const canWriteEntries = selectedAccess === 'admin' || selectedAccess === 'write'

    // Deleting needs the delete permission besides access to the namespace.
    const entryDeleteReason = missingPermission(permissions, ['vault.delete'], 'deleting secrets')

    const namespaceDeleteReason = missingPermission(permissions, ['vault.namespace.delete'], 'deleting namespaces')

    // The effects below read the latest namespaces without re-running on each poll.

    const namespacesRef = useRef(namespaces)

    useEffect(() => {

        namespacesRef.current = namespaces

    }, [namespaces])



    // Entry picked with a click; Ctrl+D deletes it.
    const [selectedEntryKey, setSelectedEntryKey] = useState<string | null>(null)

    const [entryPickerOpen, setEntryPickerOpen] = useState(false)

    const [createMenuOpen, setCreateMenuOpen] = useState(false)
    const createMenuRef = useRef<HTMLDivElement>(null)
    const [namespaceName, setNamespaceName] = useState('')
    const [visibility, setVisibility] = useState<VaultVisibility>('private')
    const [accessLevel, setAccessLevel] = useState<VaultAccess>('read')
    const [entryForm, setEntryForm] = useState<EntryForm>(emptyEntry)
    const entryValueError = vaultValueError(entryForm.value, entryForm.type)
    const [editingKey, setEditingKey] = useState<string | null>(null)
    const [detailEntry, setDetailEntry] = useState<VaultEntryWithValue | null>(
        null,
    )
    const [username, setUsername] = useState('')



    const [revealed, setRevealed] = useState<

        Record<string, VaultEntryWithValue>

    >({})



    const [loading, setLoading] = useState(true)

    const [busy, setBusy] = useState(false)

    const [error, setError] = useState('')
    useErrorToast(error)

    const [message, setMessage] = useState('')





    useEffect(() => {
        if (!createMenuOpen) return

        function handlePointerDown(event: PointerEvent) {
            if (
                event.target instanceof Node &&
                !createMenuRef.current?.contains(event.target)
            ) {
                setCreateMenuOpen(false)
            }
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') setCreateMenuOpen(false)
        }

        document.addEventListener('pointerdown', handlePointerDown)
        document.addEventListener('keydown', handleKeyDown)

        return () => {
            document.removeEventListener('pointerdown', handlePointerDown)
            document.removeEventListener('keydown', handleKeyDown)
        }
    }, [createMenuOpen])

    const refreshNamespaces = useCallback(async () => {

        const result = await vaultApi.listNamespaces()

        const items = result.items



        setNamespaces(items)



        setSelectedNamespace((current) => {

            if (current && items.some((item) => item.name === current)) {

                return current

            }



            return items[0]?.name ?? ''

        })



        return items

    }, [])



    const refreshEntries = useCallback(async (namespace: string) => {

        if (!namespace) {

            setEntries([])

            setRevealed({})

            return

        }



        const result = await vaultApi.listEntries(namespace)

        setEntries(result.items)

        setRevealed({})

    }, [])



    const refreshAccess = useCallback(async (namespace: string) => {

        if (!namespace) {

            setAccessAssignments([])

            return

        }



        const result = await vaultApi.listAccess(namespace)

        setAccessAssignments(result.items)

    }, [])



    const refreshAll = useCallback(async () => {

        setLoading(true)

        setError('')



        try {

            const items = await refreshNamespaces()

            if (pendingEntryRef.current) {

                pendingEntryRef.current = false

                const writable = items.find((item) => item.access === 'admin' || item.access === 'write')

                if (writable) {

                    setSelectedNamespace(writable.name)

                    setEditingKey(null)

                    setEntryForm(emptyEntry)

                    setModalType('entry')

                } else {

                    setError('You need write access to a namespace to add a secret.')

                }

            }

        } catch (cause) {

            setError(getErrorMessage(cause))

        } finally {

            setLoading(false)

        }

    }, [refreshNamespaces])



    useEffect(() => {

        void refreshAll()

    }, [refreshAll])



    useEffect(() => {

        if (!selectedNamespace) {

            setEntries([])

            setAccessAssignments([])

            setRevealed({})

            return

        }



        let cancelled = false



        async function loadNamespaceData() {

            setError('')



            // Only namespace administrators may read the access list.

            const admin =

                namespacesRef.current.find((namespace) => namespace.name === selectedNamespace)?.access === 'admin'

            const [entryResult, accessResult] = await Promise.allSettled([

                vaultApi.listEntries(selectedNamespace),

                admin ? vaultApi.listAccess(selectedNamespace) : Promise.resolve({ items: [] }),

            ])



            if (cancelled) {

                return

            }



            if (entryResult.status === 'fulfilled') {

                setEntries(entryResult.value.items)

                setRevealed({})

            } else {

                setEntries([])

                setError(getErrorMessage(entryResult.reason))

            }



            if (accessResult.status === 'fulfilled') {

                setAccessAssignments(accessResult.value.items)

            } else if (entryResult.status === 'fulfilled') {

                setAccessAssignments([])

                setError(getErrorMessage(accessResult.reason))

            }

        }



        void loadNamespaceData()



        return () => {

            cancelled = true

        }

    }, [selectedNamespace])



    // Automatically refresh Vault data every 5 seconds.
    useEffect(() => {
        let cancelled = false
        let inFlight = false

        async function pollVaultData() {
        if (inFlight) return

        inFlight = true

        try {
            const [namespaceResult, entryResult, accessResult] =
            await vaultApi.listNamespaces().then((namespaceList) => {
                const admin =
                    namespaceList.items.find((namespace) => namespace.name === selectedNamespace)
                        ?.access === 'admin'

                return Promise.all([
                    namespaceList,
                    selectedNamespace
                    ? vaultApi.listEntries(selectedNamespace)
                    : Promise.resolve(null),
                    selectedNamespace && admin
                    ? vaultApi.listAccess(selectedNamespace)
                    : Promise.resolve(null),
                ])
            })

            if (cancelled) return

            setNamespaces(namespaceResult.items)

            if (entryResult) {
            setEntries(entryResult.items)
            }

            if (accessResult) {
            setAccessAssignments(accessResult.items)
            }
        } catch (cause) {
            if (!cancelled) {
            setError(getErrorMessage(cause))
            }
        } finally {
            inFlight = false
        }
        }

        const intervalId = window.setInterval(() => {
        void pollVaultData()
        }, 5000)

        return () => {
        cancelled = true
        window.clearInterval(intervalId)
        }
    }, [selectedNamespace])


    function openNamespaceModal() {

        setNamespaceName('')

        setVisibility('private')

        setCreateMenuOpen(false)

        setModalType('namespace')

    }



    function openCreateEntryModal() {

        setCreateMenuOpen(false)

        if (!selectedNamespace) {

            notify.warning('Create or select a namespace first.')

            return

        }



        setEditingKey(null)

        setEntryForm(emptyEntry)

        setModalType('entry')

    }



    function closeModal() {

        setModalType(null)

        setDetailEntry(null)

        setEditingKey(null)

        setEntryForm(emptyEntry)

    }



    async function createNamespace(event: FormEvent<HTMLFormElement>) {

        event.preventDefault()



        const name = namespaceName.trim()



        if (!name) {

            notify.warning('Enter a namespace name.')

            return

        }



        setBusy(true)

        setError('')



        try {

            await vaultApi.createNamespace({
                name,
                visibility,
                })

            await refreshNamespaces()

            setSelectedNamespace(name)

            setModalType(null)

            setNamespaceName('')

            notify.success('Namespace created.')

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function saveEntry(event: FormEvent<HTMLFormElement>) {

        event.preventDefault()



        if (!selectedNamespace) {

            notify.warning('Select a namespace first.')

            return

        }



        const key = entryForm.key.trim()



        if (!key) {

            notify.warning('Enter a secret key.')

            return

        }



        let value: unknown
        try {
            value = serializeVaultValue(entryForm.value, entryForm.type)
        } catch (cause) {
            const messageText = cause instanceof Error
                ? cause.message
                : 'Enter a valid value for the selected type.'
            notify.warning(messageText)
            return
        }

        if (entryForm.value.length === 0) {
            notify.warning('Enter a value for the secret.')
            return
        }



        setBusy(true)

        setError('')



        try {

            const payload = {

                value,

                type: entryForm.type,

                sensitive: entryForm.sensitive,

            }



            if (editingKey !== null) {

                await vaultApi.updateEntry(

                    selectedNamespace,

                    editingKey,

                    payload,

                )

                notify.success('Secret updated.')

            } else {

                await vaultApi.createEntry(selectedNamespace, {

                    key,

                    ...payload,

                })

                notify.success('Secret created.')

            }



            await refreshEntries(selectedNamespace)

            setModalType(null)

            setEntryForm(emptyEntry)

            setEditingKey(null)

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function editEntry(entry: VaultEntry) {

        if (!selectedNamespace) {

            notify.warning('Select a namespace first.')

            return

        }

        setBusy(true)

        setError('')

        try {

            // The list endpoint intentionally omits secret values. Load the value

            // through the dedicated reveal endpoint before populating the edit form.

            const result = await vaultApi.revealEntry(selectedNamespace, entry.key)

            setEditingKey(entry.key)

            setEntryForm({

                key: entry.key,

                value: formatValue(result.entry.value),

                type: result.entry.type,

                sensitive: result.entry.sensitive,

            })

            setModalType('entry')

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function downloadVaultFile(key: string, filename: string) {
        try {
            await vaultApi.downloadFile(selectedNamespace, key, filename)
        } catch (error) {
            notify.error(error instanceof Error ? error.message : 'Unable to download the file.')
        }
    }

    async function revealEntry(key: string) {

        if (!selectedNamespace) {

            return

        }



        if (revealed[key]) {

            setRevealed((current) => {

                const next = { ...current }

                delete next[key]

                return next

            })

            return

        }



        setBusy(true)



        try {

            const result = await vaultApi.revealEntry(selectedNamespace, key)



            setRevealed((current) => ({
                ...current,
                [key]: result.entry,
            }))

            const matchingEntry = entries.find((entry) => entry.key === key)
            if (matchingEntry && !matchingEntry.sensitive) {
                setDetailEntry(result.entry)
                setModalType('detail')
            }

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function deleteEntry(entry: VaultEntry) {

        if (entryDeleteReason) {

            notify.error(entryDeleteReason, { title: 'Cannot delete secret' })

            return

        }

        if (!selectedNamespace) {

            return

        }



        const confirmed = await modal.confirm({

            title: 'Delete secret?',

            message: `The secret "${entry.key}" will be permanently deleted.`,

            confirmText: 'Delete',

            cancelText: 'Cancel',

            destructive: true,

        })



        if (!confirmed) {

            return

        }



        setBusy(true)

        setError('')



        try {

            await vaultApi.deleteEntry(selectedNamespace, entry.key)

            await refreshEntries(selectedNamespace)

            notify.success('Secret deleted.')

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function deleteNamespace() {

        if (namespaceDeleteReason) {

            notify.error(namespaceDeleteReason, { title: 'Cannot delete namespace' })

            return

        }

        if (!selectedNamespace) {

            return

        }



        const namespaceToDelete = selectedNamespace

        const confirmed = await modal.confirm({

            title: 'Delete namespace?',

            message: `Namespace "${namespaceToDelete}" and its associated secrets and access assignments will be deleted. This action cannot be undone.`,

            confirmText: 'Delete namespace',

            cancelText: 'Cancel',

            destructive: true,

        })



        if (!confirmed) {

            return

        }



        setBusy(true)

        setError('')



        try {

            await vaultApi.deleteNamespace(namespaceToDelete)

            setSelectedNamespace('')

            setEntries([])

            setAccessAssignments([])

            setRevealed({})

            await refreshNamespaces()

            notify.success('Namespace deleted.')

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function grantAccess(event: FormEvent<HTMLFormElement>) {

        event.preventDefault()



        if (!selectedNamespace) {

            notify.warning('Select a namespace first.')

            return

        }



        const normalizedUsername = username.trim()



        if (!normalizedUsername) {

            notify.warning('Enter a username.')

            return

        }



        setBusy(true)

        setError('')



        try {

            await vaultApi.grantAccess(selectedNamespace, {
            username: normalizedUsername,
            access: accessLevel,
            })



            await refreshAccess(selectedNamespace)

            setUsername('')

            notify.success('Namespace access updated.')

        } catch (cause) {

            const messageText = getErrorMessage(cause)

            setError(messageText)

            notify.error(messageText)

        } finally {

            setBusy(false)

        }

    }



    async function revokeAccess(assignment: VaultAccessAssignment) {

        if (!selectedNamespace || !assignment.username) {

            notify.warning('Restart the Entropy web server to revoke access from this page.')

            return

        }

        const confirmed = await modal.confirm({

            title: 'Revoke access?',

            message: `Remove ${assignment.username}'s ${assignment.access} access to ${selectedNamespace}?`,

            confirmText: 'Revoke access',

            destructive: true,

        })

        if (!confirmed) return

        setBusy(true)

        try {

            await vaultApi.revokeAccess(selectedNamespace, assignment.username)

            await refreshAccess(selectedNamespace)

            notify.success(`Access revoked for ${assignment.username}.`)

        } catch (cause) {

            notify.error(getErrorMessage(cause))

        } finally {

            setBusy(false)

        }

    }



    const openEntryShortcut = () => {

        if (!selectedNamespace) {

            notify.warning('Create or select a namespace first.')

            return

        }

        if (!canWriteEntries) {

            notify.warning(`You have read-only access to ${selectedNamespace}.`)

            return

        }

        openCreateEntryModal()

    }



    useCreateIntent('vault-entry', () => openEntryShortcut())

    useCreateIntent('vault-namespace', () => openNamespaceModal())



    useShortcuts(

        {

            'mod+n': openEntryShortcut,

            'alt+n': openEntryShortcut,

            'mod+shift+s': openNamespaceModal,

            'mod+d': () => {

                if (!selectedNamespace) return

                const selected = entries.find((entry) => entry.key === selectedEntryKey)

                if (selected) void deleteEntry(selected)

                else setEntryPickerOpen(true)

            },

            'mod+shift+d': () => {

                if (selectedNamespace && isNamespaceAdmin) void deleteNamespace()

            },

        },

        modalType === null && !entryPickerOpen && !busy,

    )



    function openEntryDetails(entry: VaultEntryWithValue) {

        setDetailEntry(entry)

        setModalType('detail')

    }



    function handleNamespaceChange(value: string) {

        setSelectedNamespace(value)

        setError('')

        setMessage('')

    }



    return (

        <section className="list-page vault-page">




            {message && (

                <div className="vault-alert vault-alert-success" role="status">

                    <span>{message}</span>

                    <button

                        type="button"

                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"

                        onClick={() => setMessage('')}

                        aria-label="Dismiss message"

                    >

                        <X size={16} />

                    </button>

                </div>

            )}



            <section className="dashboard-section list-section vault-panel">

                <div className="dashboard-section-heading list-section-heading">

                    <div>

                        <h2>

                            Vault

                            <span className="list-count" aria-label={`${namespaces.length} namespaces`}>

                                {namespaces.length}

                            </span>

                        </h2>

                        <p>

                            {selectedNamespace

                                ? `${entries.length} ${entries.length === 1 ? 'secret' : 'secrets'} in ${selectedNamespace} · ${

                                      selectedAccess ? `${selectedAccess} access` : 'read-only (shared)'

                                  }`

                                : 'Secrets grouped into namespaces you can share with other users.'}

                        </p>

                    </div>

                <div className="entropy-panel-actions vault-topbar-actions">

                    <button

                        type="button"

                        className="entropy-button entropy-button-secondary entropy-button-icon"

                        onClick={() => setPortable('import')}

                        aria-label="Import vault"

                        title="Import an .entvault export"

                    >

                        <Upload size={15} />

                    </button>

                    <button

                        type="button"

                        className="entropy-button entropy-button-secondary entropy-button-icon"

                        onClick={() => setPortable('export')}

                        aria-label="Export vault"

                        title="Export namespaces, encrypted with a passphrase"

                    >

                        <Download size={15} />

                    </button>

                    {selectedNamespace && isNamespaceAdmin && (

                        <button

                            type="button"

                            className="entropy-button entropy-button-danger"

                            onClick={() => void deleteNamespace()}

                            disabled={busy}

                            aria-disabled={namespaceDeleteReason ? true : undefined}

                            title={namespaceDeleteReason ?? 'Delete namespace (Ctrl+Shift+D)'}

                        >

                            <Trash2 size={15} />

                            Delete namespace

                        </button>

                    )}



                    <div className="vault-create-menu" ref={createMenuRef}>

                        <button

                            type="button"

                            className="entropy-button entropy-button-primary"

                            onClick={() => setCreateMenuOpen((current) => !current)}

                            aria-expanded={createMenuOpen}

                            aria-haspopup="menu"

                        >

                            <Plus size={17} />

                            <span>Create</span>

                            <ChevronDown size={15} />

                        </button>



                        {createMenuOpen && (

                            <>

                                <div className="vault-create-menu-items" role="menu">

                                    <button

                                        type="button"

                                        role="menuitem"

                                        disabled={!selectedNamespace || !canWriteEntries}

                                        onClick={openCreateEntryModal}

                                    >

                                        <KeyRound size={16} />

                                        <span>

                                            <strong>Create a vault entry</strong>

                                            <small>Add a secret to the selected namespace</small>

                                        </span>

                                    </button>

                                    <button

                                        type="button"

                                        role="menuitem"

                                        disabled={!selectedNamespace || !canWriteEntries}

                                        onClick={() => {

                                            setCreateMenuOpen(false)

                                            setFileDialog('')

                                        }}

                                    >

                                        <FileKey2 size={16} />

                                        <span>

                                            <strong>Upload a file</strong>

                                            <small>Certificate, keystore, key or any file</small>

                                        </span>

                                    </button>

                                    <button

                                        type="button"

                                        role="menuitem"

                                        disabled={!permissions?.has('vault.namespace.create')}

                                        onClick={openNamespaceModal}

                                    >

                                        <Shield size={16} />

                                        <span>

                                            <strong>Create a namespace</strong>

                                            <small>Create a new secret namespace</small>

                                        </span>

                                    </button>

                                </div>

                            </>

                        )}

                    </div>

                </div>

                </div>



                {namespaces.length > 0 && (

                    <div className="list-toolbar">

                        <label className="list-filter" htmlFor="vault-namespace-select">

                            <span>Namespace</span>

                            <select

                        id="vault-namespace-select"

                        className="entropy-select"

                        value={selectedNamespace}

                        onChange={(event) => handleNamespaceChange(event.target.value)}

                        disabled={loading || namespaces.length === 0}

                    >

                        {namespaces.length === 0 && (

                            <option value="">No namespaces available</option>

                        )}

                        {namespaces.map((namespace) => (

                            <option key={namespace.name} value={namespace.name}>

                                {namespace.name}

                            </option>

                        ))}

                    </select>

                        </label>

                    </div>

                )}



            {loading ? (

                <EntropyLoader label="Loading vault…" />

            ) : namespaces.length === 0 ? (

                <div className="vault-empty-state">

                    <div className="vault-empty-icon">

                        <LockKeyhole size={28} />

                    </div>

                    <h2>No namespaces yet</h2>

                    <p>

                        Create a namespace to start storing and managing secrets.

                    </p>

                    <button

                        type="button"

                        className="entropy-button entropy-button-primary"

                        onClick={openNamespaceModal}

                    >

                        <Plus size={16} />

                        Create a namespace

                    </button>

                </div>

            ) : (

                <>

                    <nav className="vault-tabs" aria-label="Namespace sections">

                        <button

                            type="button"

                            className={activeTab === 'secrets' ? 'active' : ''}

                            onClick={() => setActiveTab('secrets')}

                            aria-current={activeTab === 'secrets' ? 'page' : undefined}

                        >

                            <KeyRound size={16} />

                            Secrets

                            <span className="vault-tab-count">{entries.length}</span>

                        </button>

                        {isNamespaceAdmin && (

                        <button

                            type="button"

                            className={activeTab === 'access' ? 'active' : ''}

                            onClick={() => setActiveTab('access')}

                            aria-current={activeTab === 'access' ? 'page' : undefined}

                        >

                            <Shield size={16} />

                            Access

                            <span className="vault-tab-count">

                                {accessAssignments.length}

                            </span>

                        </button>

                        )}

                    </nav>



                    {activeTab === 'secrets' || !isNamespaceAdmin ? (

                        <section className="vault-content">

                            <div className="vault-section-header">

                                <div>

                                    <h3>Secrets</h3>

                                    <p>Values are revealed only when requested.</p>

                                </div>

                                <button

                                    type="button"

                                    className="entropy-button entropy-button-primary"

                                    title={canWriteEntries ? undefined : 'You have read-only access to this namespace'}

                                    onClick={openCreateEntryModal}

                                    disabled={busy || !canWriteEntries}

                                >

                                    <Plus size={16} />

                                    New secret

                                </button>

                            </div>



                            {entries.length === 0 ? (

                                <div className="vault-empty-inline">

                                    <KeyRound size={24} />

                                    <h3>No secrets in this namespace</h3>

                                    <p>Create a secret to store a value securely.</p>

                                    <button

                                        type="button"

                                        className="entropy-button entropy-button-secondary"

                                        title={canWriteEntries ? undefined : 'You have read-only access to this namespace'}

                                        disabled={!canWriteEntries}

                                        onClick={openCreateEntryModal}

                                    >

                                        <Plus size={16} />

                                        Create secret

                                    </button>

                                </div>

                            ) : (

                                <div className="list-table-wrap">

                                    <table className="list-table">

                                        <thead>

                                            <tr>

                                                <th>Key</th>

                                                <th>Type</th>

                                                <th>Storage</th>

                                                <th>Value</th>

                                                <th className="vault-actions-heading">Actions</th>

                                            </tr>

                                        </thead>

                                        <tbody>

                                            {entries.map((entry) => {
                                                const revealedEntry = revealed[entry.key]
                                                const isRevealed = Boolean(revealedEntry)
                                                const revealedValue = revealedEntry
                                                    ? formatValue(revealedEntry.value)
                                                    : ''

                                                return (
                                                    <tr

                                                        key={entry.key}

                                                        className={selectedEntryKey === entry.key ? 'is-selected' : undefined}

                                                        aria-selected={selectedEntryKey === entry.key}

                                                        onClick={() => setSelectedEntryKey(entry.key)}

                                                    >
                                                        <td>
                                                            <div className="vault-key-cell">
                                                                {entry.type === 'file' ? <FileKey2 size={15} /> : <KeyRound size={15} />}
                                                                <span>{entry.key}</span>
                                                            </div>
                                                        </td>
                                                        <td>
                                                            <span className="vault-type-badge">{entry.type}</span>
                                                        </td>
                                                        <td>
                                                            <span
                                                                className={`vault-storage-badge ${entry.sensitive
                                                                    ? 'vault-storage-encrypted'
                                                                    : 'vault-storage-plain'
                                                                    }`}
                                                            >
                                                                {entry.sensitive ? (
                                                                    <>
                                                                        <LockKeyhole size={13} />
                                                                        Encrypted
                                                                    </>
                                                                ) : (
                                                                    'Plaintext'
                                                                )}
                                                            </span>
                                                        </td>
                                                        <td className="vault-value-cell">
                                                            {entry.type === 'file' ? (
                                                                <div className="vault-file-value">
                                                                    <span title={entry.file?.content_type}>
                                                                        {entry.file?.filename ?? 'file'}
                                                                        {entry.file && <small>{fileSize(entry.file.size)}</small>}
                                                                    </span>
                                                                    <button
                                                                        type="button"
                                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                                        onClick={() => void downloadVaultFile(entry.key, entry.file?.filename ?? entry.key)}
                                                                        aria-label={`Download ${entry.key}`}
                                                                        title="Download file"
                                                                    >
                                                                        <Download size={15} />
                                                                    </button>
                                                                </div>
                                                            ) : entry.sensitive ? (
                                                                <div className="vault-hidden-value">
                                                                    <span>{isRevealed ? previewValue(revealedValue, 48) : '••••••••••••'}</span>
                                                                    <button
                                                                        type="button"
                                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                                        onClick={() => void revealEntry(entry.key)}
                                                                        disabled={busy}
                                                                        aria-label={isRevealed ? `Hide ${entry.key}` : `Reveal ${entry.key}`}
                                                                        title={isRevealed ? 'Hide value' : 'Reveal value'}
                                                                    >
                                                                        {isRevealed ? <EyeOff size={16} /> : <Eye size={16} />}
                                                                    </button>
                                                                    {isRevealed && (
                                                                        <button
                                                                            type="button"
                                                                            className="entropy-button entropy-button-link vault-value-reveal"
                                                                            onClick={() => openEntryDetails(revealedEntry)}
                                                                        >
                                                                            View full value
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            ) : isRevealed ? (
                                                                <button
                                                                    type="button"
                                                                    className="vault-value-preview clickable"
                                                                    onClick={() => openEntryDetails(revealedEntry)}
                                                                    title="View full value"
                                                                >
                                                                    {previewValue(revealedValue)}
                                                                </button>
                                                            ) : (
                                                                <button
                                                                    type="button"
                                                                    className="entropy-button entropy-button-link vault-value-reveal"
                                                                    onClick={() => void revealEntry(entry.key)}
                                                                    disabled={busy}
                                                                >
                                                                    View value
                                                                </button>
                                                            )}
                                                        </td>
                                                        <td>
                                                            <div className="vault-row-actions">
                                                                <button
                                                                    type="button"
                                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                                    onClick={() => (entry.type === 'file' ? setFileDialog(entry.key) : editEntry(entry))}
                                                                    disabled={busy || !canWriteEntries}
                                                                    aria-label={`Edit ${entry.key}`}
                                                                    title={entry.type === 'file' ? 'Replace file' : 'Edit secret'}
                                                                >
                                                                    <Pencil size={15} />
                                                                </button>
                                                                <button
                                                                    type="button"
                                                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                                    onClick={() => void deleteEntry(entry)}
                                                                    disabled={busy || !canWriteEntries}
                                                                    aria-disabled={entryDeleteReason ? true : undefined}
                                                                    aria-label={`Delete ${entry.key}`}
                                                                    title={entryDeleteReason ?? 'Delete secret'}
                                                                >
                                                                    <Trash2 size={15} />
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )
                                            })}
                                        </tbody>

                                    </table>

                                </div>

                            )}

                        </section>

                    ) : (

                        <section className="vault-content">

                            <div className="vault-section-header">

                                <div>

                                    <h3>Namespace access</h3>

                                    <p>

                                        Grant a user access to this namespace and its secrets.

                                    </p>

                                </div>

                            </div>



                            <form className="vault-access-form" onSubmit={grantAccess}>

                                <div className="vault-form-field">

                                    <label htmlFor="vault-access-username">Username</label>

                                    <UserSuggestInput

                                        id="vault-access-username"

                                        value={username}

                                        onChange={setUsername}

                                        disabled={busy}

                                    />

                                </div>



                                <div className="vault-form-field">

                                    <label htmlFor="vault-access-level">Access level</label>

                                    <select

                                        id="vault-access-level"

                                        value={accessLevel}

                                        onChange={(event) =>

                                            setAccessLevel(event.target.value as VaultAccess)

                                        }

                                    >

                                        <option value="read">Read</option>
                                        <option value="write">Write</option>
                                        <option value="admin">Admin</option>

                                    </select>

                                </div>



                                <button

                                    type="submit"

                                    className="entropy-button entropy-button-primary"

                                    disabled={busy || !username.trim()}

                                >

                                    <Plus size={16} />

                                    Grant access

                                </button>

                            </form>



                            <div className="vault-section-header vault-access-list-header">

                                <div>

                                    <h3>Access assignments</h3>

                                    <p>

                                        Users and permissions assigned to this namespace.

                                    </p>

                                </div>

                            </div>



                            {accessAssignments.length === 0 ? (

                                <div className="vault-empty-inline">

                                    <Shield size={24} />

                                    <h3>No access assignments</h3>

                                    <p>

                                        No explicit access assignments were returned for this

                                        namespace.

                                    </p>

                                </div>

                            ) : (

                                <div className="list-table-wrap">

                                    <table className="list-table">

                                        <thead>

                                            <tr>

                                                <th>User</th>

                                                <th>Access level</th>

                                                <th className="vault-actions-heading">Actions</th>

                                            </tr>

                                        </thead>

                                        <tbody>

                                            {accessAssignments.map((assignment) => (

                                                <tr key={assignment.user_id}>

                                                    <td>

                                                        <div className="vault-user-cell">

                                                            <div className="vault-user-avatar">

                                                                <Shield size={15} />

                                                            </div>

                                                            <span className="vault-user-name">

                                                                <strong>

                                                                    {assignment.username ?? `User #${assignment.user_id}`}

                                                                </strong>

                                                                {assignment.full_name && (

                                                                    <small>{assignment.full_name}</small>

                                                                )}

                                                            </span>

                                                        </div>

                                                    </td>

                                                    <td>

                                                        <span className="vault-access-badge">

                                                            {assignment.access}

                                                        </span>

                                                    </td>

                                                    <td>

                                                        <div className="vault-row-actions">

                                                            <button

                                                                type="button"

                                                                className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"

                                                                onClick={() =>

                                                                    void revokeAccess(assignment)

                                                                }

                                                                disabled={busy}

                                                                aria-label={`Revoke access for ${assignment.username ?? assignment.user_id}`}

                                                                title="Revoke access"

                                                            >

                                                                <Trash2 size={15} />

                                                            </button>

                                                        </div>

                                                    </td>

                                                </tr>

                                            ))}

                                        </tbody>

                                    </table>

                                </div>

                            )}

                        </section>

                    )}

                </>

            )}



            </section>



            {entryPickerOpen && (

                <PickerDialog

                    title="Delete which entry?"

                    subtitle={`No entry is selected. Choose the entry to delete from ${selectedNamespace}.`}

                    icon={<Trash2 size={18} />}

                    placeholder="Search entries"

                    empty="No entries match your search."

                    load={(query) =>

                        entries

                            .filter((entry) => entry.key.toLowerCase().includes(query.toLowerCase()))

                            .map((entry) => ({

                                id: entry.key,

                                label: entry.key,

                                detail: `${entry.type}${entry.sensitive ? ' · sensitive' : ''}`,

                            }))

                    }

                    onPick={(item) => {

                        const entry = entries.find((candidate) => candidate.key === item.id)

                        if (entry) void deleteEntry(entry)

                    }}

                    onClose={() => setEntryPickerOpen(false)}

                />

            )}



            {modalType === 'namespace' && (

                <div

                    className="vault-modal-backdrop"

                    role="presentation"

                    onMouseDown={(event) => {

                        if (event.target === event.currentTarget && !busy) {

                            closeModal()

                        }

                    }}

                >

                    <section

                        className="vault-modal"

                        role="dialog"

                        aria-modal="true"

                        aria-labelledby="vault-namespace-modal-title"

                    >

                        <header className="vault-modal-header">

                            <div>

                                <h2 id="vault-namespace-modal-title">Create a namespace</h2>

                                <p>Create a separate space for related secrets.</p>

                            </div>

                            <button

                                type="button"

                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"

                                onClick={closeModal}

                                disabled={busy}

                                aria-label="Close dialog"

                            >

                                <X size={18} />

                            </button>

                        </header>



                        <form onSubmit={createNamespace}>

                            <div className="vault-modal-body">

                                <div className="vault-form-field">

                                    <label htmlFor="vault-new-namespace-name">Name</label>

                                    <input

                                        id="vault-new-namespace-name"

                                        type="text"

                                        value={namespaceName}

                                        onChange={(event) => setNamespaceName(event.target.value)}

                                        placeholder="e.g. production"

                                        autoFocus

                                        required

                                    />

                                </div>



                                <div className="vault-form-field">

                                    <label htmlFor="vault-new-namespace-visibility">

                                        Visibility

                                    </label>

                                    <select

                                        id="vault-new-namespace-visibility"

                                        value={visibility}

                                        onChange={(event) =>

                                            setVisibility(event.target.value as VaultVisibility)

                                        }

                                    >

                                        <option value="private">Private</option>
                                        <option value="shared">Shared</option>

                                    </select>

                                    <p className="vault-field-help">

                                        Private namespaces restrict access according to explicit

                                        permissions. Shared visibility follows the backend's

                                        namespace access rules.

                                    </p>

                                </div>

                            </div>



                            <footer className="vault-modal-footer">

                                <button

                                    type="button"

                                    className="entropy-button entropy-button-secondary"

                                    onClick={closeModal}

                                    disabled={busy}

                                >

                                    Cancel

                                </button>

                                <button

                                    type="submit"

                                    className="entropy-button entropy-button-primary"

                                    disabled={busy || !namespaceName.trim()}

                                >

                                    {busy ? 'Creating…' : 'Create namespace'}

                                </button>

                            </footer>

                        </form>

                    </section>

                </div>

            )}



            {modalType === 'entry' && (

                <div

                    className="vault-modal-backdrop"

                    role="presentation"

                    onMouseDown={(event) => {

                        if (event.target === event.currentTarget && !busy) {

                            closeModal()

                        }

                    }}

                >

                    <section

                        className="vault-modal vault-modal-wide"

                        role="dialog"

                        aria-modal="true"

                        aria-labelledby="vault-entry-modal-title"

                    >

                        <header className="vault-modal-header">

                            <div>

                                <h2 id="vault-entry-modal-title">

                                    {editingKey === null ? 'Create a secret' : 'Edit secret'}

                                </h2>

                                <p>

                                    Namespace: <strong>{selectedNamespace}</strong>

                                </p>

                            </div>

                            <button

                                type="button"

                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"

                                onClick={closeModal}

                                disabled={busy}

                                aria-label="Close dialog"

                            >

                                <X size={18} />

                            </button>

                        </header>



                        <form onSubmit={saveEntry}>

                            <div className="vault-modal-body">

                                <div className="vault-form-grid">

                                    <div className="vault-form-field">

                                        <label htmlFor="vault-entry-key">Key / name</label>

                                        <input

                                            id="vault-entry-key"

                                            type="text"

                                            value={entryForm.key}

                                            onChange={(event) =>

                                                setEntryForm((current) => ({

                                                    ...current,

                                                    key: event.target.value,

                                                }))

                                            }

                                            placeholder="e.g. DATABASE_URL"

                                            autoFocus

                                            required

                                            disabled={busy || editingKey !== null}

                                        />

                                    </div>



                                    <div className="vault-form-field">

                                        <label htmlFor="vault-entry-type">Value type</label>

                                        <select

                                            id="vault-entry-type"

                                            value={entryForm.type}

                                            disabled={busy}

                                            onChange={(event) =>

                                                setEntryForm((current) => {
                                                    const type = event.target.value as VaultValueType
                                                    return {
                                                        ...current,
                                                        type,
                                                        value: type === 'boolean'
                                                            ? 'true'
                                                            : type === 'array'
                                                                ? '[]'
                                                                : type === 'object'
                                                                    ? '{}'
                                                                    : '',
                                                    }
                                                })

                                            }

                                        >

                                            {valueTypes.map((type) => (

                                                <option key={type} value={type}>

                                                    {type}

                                                </option>

                                            ))}
                                            {entryForm.type === 'object' && (
                                                <option value="object">object (existing)</option>
                                            )}

                                        </select>

                                    </div>

                                </div>



                                <div className="vault-form-field">

                                    <div className="vault-value-editor-heading">
                                        <label htmlFor="vault-entry-value">Value</label>
                                        {isStructuredType(entryForm.type) && (
                                            <button
                                                type="button"
                                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                                disabled={busy || !entryForm.value.trim() || Boolean(entryValueError)}
                                                onClick={() => setEntryForm((current) => ({
                                                    ...current,
                                                    value: JSON.stringify(JSON.parse(current.value), null, 2),
                                                }))}
                                            >
                                                Format JSON
                                            </button>
                                        )}
                                    </div>

                                    {entryForm.type === 'string' ? (
                                    <textarea

                                        id="vault-entry-value"
                                        className={isStructuredType(entryForm.type) ? 'vault-json-editor' : undefined}

                                        value={entryForm.value}

                                        disabled={busy}

                                        onChange={(event) =>

                                            setEntryForm((current) => ({

                                                ...current,

                                                value: event.target.value,

                                            }))

                                        }

                                        placeholder={

                                            editingKey !== null

                                                ? 'Enter the replacement value'

                                                : entryForm.type === 'string'

                                                    ? 'Enter the secret value'

                                                    : 'Enter a valid JSON value'

                                        }

                                        rows={isStructuredType(entryForm.type) ? 8 : 4}

                                        required

                                        spellCheck={false}
                                        aria-invalid={Boolean(entryValueError)}
                                        aria-describedby={entryValueError ? 'vault-entry-value-error' : 'vault-entry-value-help'}

                                    />
                                    ) : entryForm.type === 'number' ? (
                                        <input
                                            id="vault-entry-value"
                                            type="text"
                                            inputMode="decimal"
                                            className="vault-number-input"
                                            value={entryForm.value}
                                            disabled={busy}
                                            onChange={(event) => setEntryForm((current) => ({
                                                ...current,
                                                value: event.target.value,
                                            }))}
                                            placeholder="e.g. 42 or 3.14"
                                            autoComplete="off"
                                            spellCheck={false}
                                            required
                                            aria-invalid={Boolean(entryValueError)}
                                            aria-describedby={entryValueError ? 'vault-entry-value-error' : 'vault-entry-value-help'}
                                        />
                                    ) : entryForm.type === 'boolean' ? (
                                        <select
                                            id="vault-entry-value"
                                            value={entryForm.value}
                                            disabled={busy}
                                            onChange={(event) => setEntryForm((current) => ({
                                                ...current,
                                                value: event.target.value,
                                            }))}
                                            aria-describedby="vault-entry-value-help"
                                        >
                                            <option value="true">true</option>
                                            <option value="false">false</option>
                                        </select>
                                    ) : (
                                        <div className="vault-json-editor-frame" aria-invalid={Boolean(entryValueError)}>
                                            <Editor
                                                path="vault-secret-value.json"
                                                value={entryForm.value}
                                                language="json"
                                                theme={monacoTheme}
                                                onChange={(value) => setEntryForm((current) => ({
                                                    ...current,
                                                    value: value ?? '',
                                                }))}
                                                options={{
                                                    ariaLabel: entryForm.type === 'array'
                                                        ? 'Secret JSON array value'
                                                        : 'Secret JSON value',
                                                    automaticLayout: true,
                                                    fontSize: 13,
                                                    minimap: { enabled: false },
                                                    readOnly: busy,
                                                    scrollBeyondLastLine: false,
                                                    tabSize: 2,
                                                    wordWrap: 'on',
                                                }}
                                            />
                                        </div>
                                    )}

                                    {entryValueError && (
                                        <p className="vault-field-error" id="vault-entry-value-error" role="alert">
                                            {entryValueError}
                                        </p>
                                    )}
                                    <p className="vault-field-help" id="vault-entry-value-help">

                                        {editingKey !== null

                                            ? 'For safety, the current value is not prefilled. Enter the replacement value.'

                                            : entryForm.type === 'string'

                                                ? 'Text is stored as a string.'

                                                : entryForm.type === 'number'
                                                    ? 'Enter one finite number. The value is strictly validated.'
                                                    : entryForm.type === 'boolean'
                                                        ? 'Choose true or false.'
                                                        : entryForm.type === 'array'
                                                            ? 'Enter a valid JSON array, for example [1, "two"].'
                                                            : 'Enter valid JSON matching the selected type.'}

                                    </p>

                                </div>



                                <label className="vault-checkbox-row">

                                    <input

                                        type="checkbox"

                                        checked={entryForm.sensitive}

                                        disabled={busy}

                                        onChange={(event) =>

                                            setEntryForm((current) => ({

                                                ...current,

                                                sensitive: event.target.checked,

                                            }))

                                        }

                                    />

                                    <span className="vault-checkbox-icon">

                                        <LockKeyhole size={16} />

                                    </span>

                                    <span>

                                        <strong>Encrypt this value</strong>

                                        <small>

                                            Keep this enabled for credentials, tokens, and other

                                            sensitive data.

                                        </small>

                                    </span>

                                </label>

                            </div>



                            <footer className="vault-modal-footer">

                                <button

                                    type="button"

                                    className="entropy-button entropy-button-secondary"

                                    onClick={closeModal}

                                    disabled={busy}

                                >

                                    Cancel

                                </button>

                                <button

                                    type="submit"

                                    className="entropy-button entropy-button-primary"

                                    disabled={busy}

                                >

                                    {busy

                                        ? 'Saving…'

                                        : editingKey !== null

                                            ? 'Save changes'

                                            : 'Create secret'}

                                </button>

                            </footer>

                        </form>

                    </section>

                </div>

            )}



            {modalType === 'detail' && detailEntry && (

                <div

                    className="vault-modal-backdrop"

                    role="presentation"

                    onMouseDown={(event) => {

                        if (event.target === event.currentTarget) {

                            closeModal()

                        }

                    }}

                >

                    <section

                        className="vault-modal vault-modal-wide"

                        role="dialog"

                        aria-modal="true"

                        aria-labelledby="vault-detail-modal-title"

                    >

                        <header className="vault-modal-header">

                            <div>

                                <h2 id="vault-detail-modal-title">{detailEntry.key}</h2>

                                <p>

                                    {detailEntry.type}

                                    {' · '}

                                    {detailEntry.sensitive ? 'Encrypted' : 'Plaintext'}

                                </p>

                            </div>

                            <button

                                type="button"

                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"

                                onClick={closeModal}

                                aria-label="Close dialog"

                            >

                                <X size={18} />

                            </button>

                        </header>



                        <div className="vault-modal-body">

                            <div className="vault-detail-value">

                                {isStructuredType(detailEntry.type) && (

                                    <div className="vault-detail-value-label">

                                        <FileJson size={15} />

                                        Full value

                                    </div>

                                )}

                                <pre>{formatValue(detailEntry.value)}</pre>

                            </div>

                            <button

                                type="button"

                                className="entropy-button entropy-button-secondary"

                                onClick={() =>

                                    void navigator.clipboard

                                        .writeText(formatValue(detailEntry.value))

                                        .then(() => notify.success('Value copied.'))

                                        .catch(() =>

                                            notify.error('Could not copy the value to clipboard.'),

                                        )

                                }

                            >

                                Copy value

                            </button>

                        </div>



                        <footer className="vault-modal-footer">

                            <button

                                type="button"

                                className="entropy-button entropy-button-primary"

                                onClick={closeModal}

                            >

                                Close

                            </button>

                        </footer>

                    </section>

                </div>

            )}

            {portable === 'export' && (

                <VaultExportDialog preselected={selectedNamespace || null} onClose={() => setPortable(null)} />

            )}

            {fileDialog !== null && selectedNamespace && (
                <VaultFileDialog
                    namespace={selectedNamespace}
                    replaceKey={fileDialog || undefined}
                    onClose={() => setFileDialog(null)}
                    onSaved={() => void refreshEntries(selectedNamespace)}
                />
            )}
            {portable === 'import' && (

                <VaultImportDialog onClose={() => setPortable(null)} onDone={() => void refreshNamespaces()} />

            )}

        </section>

    )

}
