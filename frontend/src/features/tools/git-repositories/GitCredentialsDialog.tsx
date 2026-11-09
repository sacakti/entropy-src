import { useEffect, useState, type FormEvent } from 'react'
import { KeyRound, Save, Trash2 } from 'lucide-react'
import { apiRequest } from '../../../services/api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import Dialog from '../../../components/layout/Dialog'
import EntropyLoader from '../../../components/feedback/EntropyLoader'

type Identity = { name: string; email: string }
type Credential = { host: string; username: string; updated_at: string }
type CredentialData = { identity: Identity | null; default_identity: Identity; credentials: Credential[] }

export default function GitCredentialsDialog({ initialHost = '', onClose, onSaved }: {
    initialHost?: string
    onClose: () => void
    onSaved?: () => void
}) {
    const { notify, modal } = useFeedback()
    const [data, setData] = useState<CredentialData | null>(null)
    const [name, setName] = useState('')
    const [email, setEmail] = useState('')
    const [host, setHost] = useState(initialHost)
    const [username, setUsername] = useState('')
    const [token, setToken] = useState('')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
        void apiRequest<CredentialData>('/api/git-repositories/credentials').then((result) => {
            setData(result)
            setName(result.identity?.name ?? '')
            setEmail(result.identity?.email ?? '')
            const saved = result.credentials.find((item) => item.host === initialHost)
            if (saved) setUsername(saved.username)
        }).catch((reason: Error) => setError(reason.message))
    }, [initialHost])

    const saveIdentity = async (event: FormEvent) => {
        event.preventDefault()
        setBusy(true); setError('')
        try {
            const result = await apiRequest<{ identity: Identity }>('/api/git-repositories/credentials/identity', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email }),
            })
            setData((current) => current && { ...current, identity: result.identity })
            notify.success(`Commits will be authored as ${result.identity.name} <${result.identity.email}>.`, { title: 'Git identity saved' })
            onSaved?.()
        } catch (reason) { setError((reason as Error).message) }
        finally { setBusy(false) }
    }

    const saveCredential = async (event: FormEvent) => {
        event.preventDefault()
        setBusy(true); setError('')
        try {
            const result = await apiRequest<{ credentials: Credential[] }>('/api/git-repositories/credentials/hosts', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, username, token }),
            })
            setData((current) => current && { ...current, credentials: result.credentials })
            setToken('')
            notify.success(`Token saved for ${host.trim()}.`, { title: 'Git credential saved' })
            onSaved?.()
        } catch (reason) { setError((reason as Error).message) }
        finally { setBusy(false) }
    }

    const removeCredential = async (credential: Credential) => {
        const confirmed = await modal.confirm({
            title: 'Remove Git credential?',
            message: `Remove your saved token for ${credential.host}? Pull and push to private HTTPS remotes on this host will stop working for you.`,
            confirmText: 'Remove credential', destructive: true,
        })
        if (!confirmed) return
        try {
            await apiRequest(`/api/git-repositories/credentials/hosts/${encodeURIComponent(credential.host)}`, { method: 'DELETE' })
            setData((current) => current && { ...current, credentials: current.credentials.filter((item) => item.host !== credential.host) })
            onSaved?.()
        } catch (reason) { setError((reason as Error).message) }
    }

    return <Dialog title="Git credentials" subtitle="Your commit identity and access tokens. Only you can use them; tokens are encrypted and never shown again." icon={<KeyRound size={18} />} onClose={onClose} className="git-credentials-dialog" footer={<button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>Close</button>}>
        {!data ? (error ? <div className="entropy-alert entropy-alert-error" role="alert">{error}</div> : <EntropyLoader label="Loading Git credentials…" />) : <div className="git-credentials">
            {error && <div className="entropy-alert entropy-alert-error" role="alert">{error}</div>}
            <form className="git-browser-create-file-form" onSubmit={(event) => void saveIdentity(event)}>
                <h4>Commit identity</h4>
                <label>Name<input value={name} onChange={(event) => setName(event.target.value)} placeholder={data.default_identity.name} maxLength={255} required /></label>
                <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" maxLength={320} required /></label>
                <small>{data.identity ? 'Used as author and committer of the changes you save in the repository browser.' : `Not set: commits use ${data.default_identity.name} <${data.default_identity.email}>. Use the email of your Git host account so commits link to you.`}</small>
                <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy}><Save size={15} /> Save identity</button>
            </form>
            <form className="git-browser-create-file-form" onSubmit={(event) => void saveCredential(event)}>
                <h4>HTTPS access tokens</h4>
                {data.credentials.length ? <ul className="git-credentials-list">{data.credentials.map((credential) => <li key={credential.host}><span><strong>{credential.host}</strong> · {credential.username}</span><button type="button" className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm" onClick={() => void removeCredential(credential)} title={`Remove credential for ${credential.host}`}><Trash2 size={15} /></button></li>)}</ul> : <small>No tokens saved.</small>}
                <label>Host<input value={host} onChange={(event) => setHost(event.target.value)} placeholder="github.com" maxLength={255} required /></label>
                <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="your-github-username" maxLength={255} autoComplete="off" required /></label>
                <label>Personal access token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} maxLength={4096} autoComplete="new-password" required /></label>
                <small>For GitHub, create a fine-grained token with Contents: read and write access to the repositories. Saving again for the same host replaces the token. SSH remotes use the Entropy server’s SSH key instead.</small>
                <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy || !host.trim() || !username.trim() || !token.trim()}><KeyRound size={15} /> Save token</button>
            </form>
        </div>}
    </Dialog>
}
