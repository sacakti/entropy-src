import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
    Archive,
    Database,
    Globe,
    KeyRound,
    LoaderCircle,
    Mail,
    Plus,
    Save,
    Send,
    ShieldCheck,
    Trash2,
    Users,
} from 'lucide-react'

import {
    settingsApi,
    type AllSettings,
    type GroupMapping,
    type LdapSettings,
    type LdapTestResult,
    type OidcSettings,
    type RetentionSettings,
    type SectionName,
    type SmtpSettings,
} from '../../api/settings.api'
import { apiRequest } from '../../services/api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import '../../styles/admin-settings.css'
import DatabasePanel from './DatabasePanel'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

type Tab = 'general' | 'smtp' | 'ldap' | 'oidc' | 'retention' | 'database'

const TABS: { id: Tab; label: string; icon: typeof Mail; hint: string }[] = [
    { id: 'smtp', label: 'E-mail', icon: Mail, hint: 'SMTP server for alerts and messages' },
    { id: 'ldap', label: 'LDAP / Active Directory', icon: Users, hint: 'Sign in with directory accounts' },
    { id: 'oidc', label: 'Single sign-on', icon: KeyRound, hint: 'OpenID Connect (Keycloak, Azure AD, Okta)' },
    { id: 'retention', label: 'Data retention', icon: Archive, hint: 'Archive and purge old runs' },
    { id: 'database', label: 'Database', icon: Database, hint: 'Backups, checks and recovery' },
    { id: 'general', label: 'Address', icon: Globe, hint: 'Where people open Entropy' },
]

function message(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

function Field({ label, hint, children, wide }: { label: string; hint?: string; children: ReactNode; wide?: boolean }) {
    return (
        <label className={`admin-field${wide ? ' admin-field-wide' : ''}`}>
            <span>{label}</span>
            {children}
            {hint && <small>{hint}</small>}
        </label>
    )
}

function Toggle({
    checked,
    onChange,
    children,
}: {
    checked: boolean
    onChange: (value: boolean) => void
    children: ReactNode
}) {
    return (
        <label className="settings-toggle admin-field-wide">
            <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
            <span>{children}</span>
        </label>
    )
}

/** A password field: empty keeps the saved secret; "Remove" clears it. */
function SecretField({
    label,
    isSet,
    value,
    onChange,
    onClear,
}: {
    label: string
    isSet: boolean
    value: string
    onChange: (value: string) => void
    onClear: () => void
}) {
    return (
        <Field label={label} hint={isSet ? 'Saved. Leave empty to keep it, or type a new one.' : undefined}>
            <span className="settings-secret">
                <input
                    type="password"
                    autoComplete="new-password"
                    value={value}
                    placeholder={isSet ? '•••••••• (saved)' : ''}
                    onChange={(event) => onChange(event.target.value)}
                />
                {isSet && (
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={onClear}>
                        Remove
                    </button>
                )}
            </span>
        </Field>
    )
}

function Mappings({
    value,
    groups,
    externalLabel,
    onChange,
}: {
    value: GroupMapping[]
    groups: string[]
    externalLabel: string
    onChange: (value: GroupMapping[]) => void
}) {
    return (
        <div className="settings-mappings admin-field-wide">
            <span className="settings-mappings-label">Group mappings</span>
            <small>
                People in an outside group join the Entropy group mapped to it when they sign in. Give the
                Entropy groups their roles and projects in Groups.
            </small>
            {value.map((mapping, index) => (
                <div key={index} className="settings-mapping-row">
                    <input
                        value={mapping.external}
                        placeholder={externalLabel}
                        onChange={(event) =>
                            onChange(value.map((item, at) => (at === index ? { ...item, external: event.target.value } : item)))
                        }
                    />
                    <span aria-hidden="true">→</span>
                    <select
                        className="entropy-select"
                        value={mapping.group}
                        onChange={(event) =>
                            onChange(value.map((item, at) => (at === index ? { ...item, group: event.target.value } : item)))
                        }
                    >
                        <option value="">Entropy group…</option>
                        {groups.map((group) => (
                            <option key={group} value={group}>
                                {group}
                            </option>
                        ))}
                    </select>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label="Remove mapping"
                        onClick={() => onChange(value.filter((_, at) => at !== index))}
                    >
                        <Trash2 size={14} />
                    </button>
                </div>
            ))}
            <button
                type="button"
                className="entropy-button entropy-button-secondary entropy-button-sm settings-add"
                onClick={() => onChange([...value, { external: '', group: '' }])}
            >
                <Plus size={14} /> Add mapping
            </button>
        </div>
    )
}

/**
 * Administration -> Settings: e-mail, sign-in with LDAP / single sign-on,
 * data retention and the public address.
 */
export default function AdminSettings() {
    const { notify, modal } = useFeedback()
    const [settings, setSettings] = useState<AllSettings | null>(null)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [tab, setTab] = useState<Tab>('smtp')
    const [saving, setSaving] = useState(false)
    const [groups, setGroups] = useState<string[]>([])
    // Secrets typed but not yet saved; null = keep, '' = remove.
    const [secrets, setSecrets] = useState<Record<string, string | null>>({})
    const [testTo, setTestTo] = useState('')
    const [ldapTest, setLdapTest] = useState({ username: '', password: '' })
    const [ldapResult, setLdapResult] = useState<LdapTestResult | null>(null)
    const [busy, setBusy] = useState<string | null>(null)

    useEffect(() => {
        settingsApi
            .all()
            .then(setSettings)
            .catch((cause: unknown) => setError(message(cause, 'Unable to load the settings.')))
        apiRequest<{ items: { name: string }[] }>('/api/admin/groups')
            .then((result) => setGroups(result.items.map((item) => item.name)))
            .catch(() => setGroups([]))
    }, [])

    const update = <K extends keyof AllSettings>(section: K, patch: Partial<AllSettings[K]>) =>
        setSettings((current) => (current ? { ...current, [section]: { ...current[section], ...patch } } : current))

    const secretValue = (key: string) => secrets[key] ?? ''

    const save = async (section: SectionName) => {
        if (!settings) return
        setSaving(true)
        try {
            const values: Record<string, unknown> = { ...settings[section] }
            for (const name of ['password', 'bind_password', 'client_secret']) {
                if (!(name in values)) continue
                const typed = secrets[`${section}.${name}`]
                // Untouched secrets are kept on the server.
                values[name] = typed === undefined ? null : typed
                delete values[`${name}_set`]
            }
            const saved = await settingsApi.save(section, values)
            setSettings((current) => (current ? { ...current, [section]: saved } : current))
            setSecrets((current) =>
                Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${section}.`))),
            )
            notify.success('Settings saved.')
        } catch (cause) {
            notify.error(message(cause, 'Unable to save the settings.'), { title: 'Not saved' })
        } finally {
            setSaving(false)
        }
    }

    const sendTest = async () => {
        setBusy('mail')
        try {
            const result = await settingsApi.testMail(testTo.trim() || null)
            notify.success(`Test e-mail sent to ${result.sent_to.join(', ')}.`)
        } catch (cause) {
            notify.error(message(cause, 'The test e-mail was not sent.'), { title: 'E-mail failed' })
        } finally {
            setBusy(null)
        }
    }

    const testLdap = async () => {
        setBusy('ldap')
        setLdapResult(null)
        try {
            setLdapResult(await settingsApi.testLdap(ldapTest.username, ldapTest.password))
        } catch (cause) {
            notify.error(message(cause, 'The LDAP test failed.'), { title: 'LDAP' })
        } finally {
            setBusy(null)
        }
    }

    const testOidc = async () => {
        setBusy('oidc')
        try {
            const result = await settingsApi.testOidc()
            await modal.alert({
                title: 'Identity provider found',
                message: `Issuer ${result.issuer} answers. Register this redirect URI with it: ${result.redirect_uri}`,
            })
        } catch (cause) {
            notify.error(message(cause, 'The identity provider could not be reached.'), { title: 'Single sign-on' })
        } finally {
            setBusy(null)
        }
    }

    const saveRetention = async () => {
        if (!settings) return
        setSaving(true)
        try {
            const { archive_after_days, purge_archive_after_days, notifications_keep_days } = settings.retention
            const saved = await settingsApi.saveRetention({
                archive_after_days,
                purge_archive_after_days,
                notifications_keep_days,
            })
            update('retention', saved)
            notify.success('Retention saved.')
        } catch (cause) {
            notify.error(message(cause, 'Unable to save retention.'), { title: 'Not saved' })
        } finally {
            setSaving(false)
        }
    }

    const runRetention = async () => {
        const confirmed = await modal.confirm({
            title: 'Archive and purge now?',
            message:
                'Finished runs older than the archive age move to the archive, archived runs older than the purge age and old notifications are deleted. Deleted data cannot be recovered.',
            confirmText: 'Run now',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        setBusy('retention')
        try {
            const { result, retention } = await settingsApi.runRetention()
            update('retention', retention)
            notify.success(
                `Archived ${result.archived_jobs} runs, purged ${result.purged_jobs}, removed ${result.removed_notifications} notifications and ${result.removed_logs} logs.`,
                { title: 'Housekeeping done' },
            )
        } catch (cause) {
            notify.error(message(cause, 'Housekeeping failed.'))
        } finally {
            setBusy(null)
        }
    }

    const redirectUri = useMemo(() => `${window.location.origin}/api/auth/oidc/callback`, [])

    if (error) {
        return (
            <p className="entropy-unavailable">Not available.</p>
        )
    }

    if (!settings) {
        return (
            <EntropyLoader label={`Loading settings…`} />
        )
    }

    const smtp: SmtpSettings = settings.smtp
    const ldap: LdapSettings = settings.ldap
    const oidc: OidcSettings = settings.oidc
    const retention: RetentionSettings = settings.retention

    const saveButton = (section: SectionName) => (
        <button
            type="button"
            className="entropy-button entropy-button-primary"
            onClick={() => void save(section)}
            disabled={saving}
        >
            {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Save size={15} />}
            Save
        </button>
    )

    return (
        <div className="settings-admin">
            <nav className="settings-admin-tabs" aria-label="Settings sections">
                {TABS.map(({ id, label, icon: Icon, hint }) => (
                    <button
                        key={id}
                        type="button"
                        className={tab === id ? 'is-active' : ''}
                        aria-current={tab === id ? 'page' : undefined}
                        onClick={() => setTab(id)}
                    >
                        <Icon size={17} aria-hidden="true" />
                        <span>
                            <strong>{label}</strong>
                            <small>{hint}</small>
                        </span>
                        {id === 'smtp' && smtp.enabled && <span className="settings-on">On</span>}
                        {id === 'ldap' && ldap.enabled && <span className="settings-on">On</span>}
                        {id === 'oidc' && oidc.enabled && <span className="settings-on">On</span>}
                    </button>
                ))}
            </nav>

            <section className="settings-admin-panel dashboard-section">
                {tab === 'smtp' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>E-mail</h2>
                                <p>Used for run alerts set on workflows and schedules, and for test messages.</p>
                            </div>
                            {saveButton('smtp')}
                        </header>
                        <div className="settings-grid">
                            <Toggle checked={smtp.enabled} onChange={(enabled) => update('smtp', { enabled })}>
                                Send e-mail
                            </Toggle>
                            <Field label="SMTP server">
                                <input value={smtp.host} onChange={(event) => update('smtp', { host: event.target.value })} placeholder="smtp.example.com" />
                            </Field>
                            <Field label="Port">
                                <input
                                    type="number"
                                    min={1}
                                    max={65535}
                                    value={smtp.port}
                                    onChange={(event) => update('smtp', { port: Number(event.target.value) })}
                                />
                            </Field>
                            <Field label="Security" hint="STARTTLS on 587, SSL/TLS on 465, none on 25 (inside trusted networks only).">
                                <select
                                    className="entropy-select"
                                    value={smtp.security}
                                    onChange={(event) => update('smtp', { security: event.target.value as SmtpSettings['security'] })}
                                >
                                    <option value="starttls">STARTTLS</option>
                                    <option value="ssl">SSL/TLS</option>
                                    <option value="none">None</option>
                                </select>
                            </Field>
                            <Field label="User name" hint="Leave empty when the server needs no sign-in.">
                                <input value={smtp.username} autoComplete="off" onChange={(event) => update('smtp', { username: event.target.value })} />
                            </Field>
                            <SecretField
                                label="Password"
                                isSet={smtp.password_set && secrets['smtp.password'] !== ''}
                                value={secretValue('smtp.password')}
                                onChange={(value) => setSecrets((current) => ({ ...current, 'smtp.password': value }))}
                                onClear={() => setSecrets((current) => ({ ...current, 'smtp.password': '' }))}
                            />
                            <Field label="From address">
                                <input value={smtp.from_address} onChange={(event) => update('smtp', { from_address: event.target.value })} placeholder="entropy@example.com" />
                            </Field>
                            <Field label="From name">
                                <input value={smtp.from_name} onChange={(event) => update('smtp', { from_name: event.target.value })} />
                            </Field>
                            <Toggle checked={smtp.verify_tls} onChange={(verify_tls) => update('smtp', { verify_tls })}>
                                Verify the server's TLS certificate
                            </Toggle>
                        </div>
                        <div className="settings-test">
                            <strong>Send a test e-mail</strong>
                            <span>Uses the saved settings. Save first if you changed them.</span>
                            <div>
                                <input value={testTo} onChange={(event) => setTestTo(event.target.value)} placeholder="you@example.com (default: your profile address)" />
                                <button type="button" className="entropy-button entropy-button-secondary" onClick={() => void sendTest()} disabled={busy !== null}>
                                    {busy === 'mail' ? <LoaderCircle size={15} className="entropy-spin" /> : <Send size={15} />}
                                    Send test
                                </button>
                            </div>
                        </div>
                    </>
                )}

                {tab === 'ldap' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>LDAP / Active Directory</h2>
                                <p>
                                    People sign in with their directory user name and password. Entropy accounts are
                                    created on first sign-in; directory groups map to Entropy groups.
                                </p>
                            </div>
                            {saveButton('ldap')}
                        </header>
                        <div className="settings-grid">
                            <Toggle checked={ldap.enabled} onChange={(enabled) => update('ldap', { enabled })}>
                                Allow sign-in with LDAP
                            </Toggle>
                            <Field label="Server URL" hint="ldap://host:389 or ldaps://host:636" wide>
                                <input value={ldap.server_url} onChange={(event) => update('ldap', { server_url: event.target.value })} placeholder="ldaps://dc1.example.com:636" />
                            </Field>
                            <Toggle checked={ldap.start_tls} onChange={(start_tls) => update('ldap', { start_tls })}>
                                Use STARTTLS on ldap://
                            </Toggle>
                            <Toggle checked={ldap.verify_tls} onChange={(verify_tls) => update('ldap', { verify_tls })}>
                                Verify the server's TLS certificate
                            </Toggle>
                            <Field label="Bind DN" hint="Service account used to find users; empty for anonymous search.">
                                <input value={ldap.bind_dn} onChange={(event) => update('ldap', { bind_dn: event.target.value })} placeholder="cn=entropy,ou=services,dc=example,dc=com" />
                            </Field>
                            <SecretField
                                label="Bind password"
                                isSet={ldap.bind_password_set && secrets['ldap.bind_password'] !== ''}
                                value={secretValue('ldap.bind_password')}
                                onChange={(value) => setSecrets((current) => ({ ...current, 'ldap.bind_password': value }))}
                                onClear={() => setSecrets((current) => ({ ...current, 'ldap.bind_password': '' }))}
                            />
                            <Field label="User base DN">
                                <input value={ldap.user_base_dn} onChange={(event) => update('ldap', { user_base_dn: event.target.value })} placeholder="ou=people,dc=example,dc=com" />
                            </Field>
                            <Field label="User filter" hint="{username} is replaced. Active Directory: (sAMAccountName={username})">
                                <input value={ldap.user_filter} onChange={(event) => update('ldap', { user_filter: event.target.value })} />
                            </Field>
                            <Field label="User name attribute">
                                <input value={ldap.attr_username} onChange={(event) => update('ldap', { attr_username: event.target.value })} />
                            </Field>
                            <Field label="Full name attribute">
                                <input value={ldap.attr_full_name} onChange={(event) => update('ldap', { attr_full_name: event.target.value })} />
                            </Field>
                            <Field label="E-mail attribute">
                                <input value={ldap.attr_email} onChange={(event) => update('ldap', { attr_email: event.target.value })} />
                            </Field>
                            <Field label="Group attribute" hint="Attribute on the user listing their groups (memberOf).">
                                <input value={ldap.group_attribute} onChange={(event) => update('ldap', { group_attribute: event.target.value })} />
                            </Field>
                            <Toggle checked={ldap.auto_create_users} onChange={(auto_create_users) => update('ldap', { auto_create_users })}>
                                Create Entropy accounts on first sign-in
                            </Toggle>
                            <Mappings
                                value={ldap.group_mappings}
                                groups={groups}
                                externalLabel="LDAP group DN"
                                onChange={(group_mappings) => update('ldap', { group_mappings })}
                            />
                        </div>
                        <div className="settings-test">
                            <strong>Test with an account</strong>
                            <span>Finds the user with the saved settings; with a password, also checks it.</span>
                            <div>
                                <input value={ldapTest.username} onChange={(event) => setLdapTest((current) => ({ ...current, username: event.target.value }))} placeholder="user name" autoComplete="off" />
                                <input type="password" value={ldapTest.password} onChange={(event) => setLdapTest((current) => ({ ...current, password: event.target.value }))} placeholder="password (optional)" autoComplete="new-password" />
                                <button type="button" className="entropy-button entropy-button-secondary" onClick={() => void testLdap()} disabled={busy !== null || !ldapTest.username.trim()}>
                                    {busy === 'ldap' ? <LoaderCircle size={15} className="entropy-spin" /> : <ShieldCheck size={15} />}
                                    Test
                                </button>
                            </div>
                            {ldapResult && (
                                <dl className="settings-test-result">
                                    <div>
                                        <dt>Found</dt>
                                        <dd>{ldapResult.found ? ldapResult.dn : 'No such user'}</dd>
                                    </div>
                                    {ldapResult.authenticated !== null && (
                                        <div>
                                            <dt>Password</dt>
                                            <dd>{ldapResult.authenticated ? 'Accepted' : 'Refused'}</dd>
                                        </div>
                                    )}
                                    {ldapResult.found && (
                                        <>
                                            <div>
                                                <dt>Name, e-mail</dt>
                                                <dd>
                                                    {ldapResult.full_name || '—'}, {ldapResult.email || '—'}
                                                </dd>
                                            </div>
                                            <div>
                                                <dt>Entropy groups</dt>
                                                <dd>{ldapResult.mapped_groups.join(', ') || 'None mapped'}</dd>
                                            </div>
                                        </>
                                    )}
                                </dl>
                            )}
                        </div>
                    </>
                )}

                {tab === 'oidc' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>Single sign-on (OpenID Connect)</h2>
                                <p>
                                    Adds a sign-in button for your identity provider: Keycloak / Red Hat SSO, Azure AD
                                    (Entra ID), Okta, Google and others.
                                </p>
                            </div>
                            {saveButton('oidc')}
                        </header>
                        <div className="settings-grid">
                            <Toggle checked={oidc.enabled} onChange={(enabled) => update('oidc', { enabled })}>
                                Show the single sign-on button
                            </Toggle>
                            <Field label="Issuer URL" hint="Its /.well-known/openid-configuration must be reachable from the server." wide>
                                <input value={oidc.issuer} onChange={(event) => update('oidc', { issuer: event.target.value })} placeholder="https://sso.example.com/realms/acme" />
                            </Field>
                            <Field label="Client ID">
                                <input value={oidc.client_id} onChange={(event) => update('oidc', { client_id: event.target.value })} />
                            </Field>
                            <SecretField
                                label="Client secret"
                                isSet={oidc.client_secret_set && secrets['oidc.client_secret'] !== ''}
                                value={secretValue('oidc.client_secret')}
                                onChange={(value) => setSecrets((current) => ({ ...current, 'oidc.client_secret': value }))}
                                onClear={() => setSecrets((current) => ({ ...current, 'oidc.client_secret': '' }))}
                            />
                            <Field label="Redirect URI" hint="Register this with the identity provider." wide>
                                <input value={redirectUri} readOnly onFocus={(event) => event.target.select()} />
                            </Field>
                            <Field label="Button label">
                                <input value={oidc.button_label} onChange={(event) => update('oidc', { button_label: event.target.value })} />
                            </Field>
                            <Field label="Scopes">
                                <input value={oidc.scopes} onChange={(event) => update('oidc', { scopes: event.target.value })} />
                            </Field>
                            <Field label="User name claim">
                                <input value={oidc.claim_username} onChange={(event) => update('oidc', { claim_username: event.target.value })} />
                            </Field>
                            <Field label="Full name claim">
                                <input value={oidc.claim_full_name} onChange={(event) => update('oidc', { claim_full_name: event.target.value })} />
                            </Field>
                            <Field label="E-mail claim">
                                <input value={oidc.claim_email} onChange={(event) => update('oidc', { claim_email: event.target.value })} />
                            </Field>
                            <Field label="Groups claim">
                                <input value={oidc.claim_groups} onChange={(event) => update('oidc', { claim_groups: event.target.value })} />
                            </Field>
                            <Toggle checked={oidc.auto_create_users} onChange={(auto_create_users) => update('oidc', { auto_create_users })}>
                                Create Entropy accounts on first sign-in
                            </Toggle>
                            <Toggle checked={oidc.verify_tls} onChange={(verify_tls) => update('oidc', { verify_tls })}>
                                Verify the identity provider's TLS certificate
                            </Toggle>
                            <Mappings
                                value={oidc.group_mappings}
                                groups={groups}
                                externalLabel="Identity provider group"
                                onChange={(group_mappings) => update('oidc', { group_mappings })}
                            />
                        </div>
                        <div className="settings-test">
                            <strong>Check the identity provider</strong>
                            <span>Reads the issuer's configuration with the saved settings.</span>
                            <div>
                                <button type="button" className="entropy-button entropy-button-secondary" onClick={() => void testOidc()} disabled={busy !== null}>
                                    {busy === 'oidc' ? <LoaderCircle size={15} className="entropy-spin" /> : <ShieldCheck size={15} />}
                                    Check
                                </button>
                            </div>
                        </div>
                    </>
                )}

                {tab === 'database' && <DatabasePanel />}
                {tab === 'retention' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>Data retention</h2>
                                <p>
                                    Entropy archives and purges on its own every hour with these settings. Archived runs
                                    no longer show in Runs; purged data is gone for good.
                                </p>
                            </div>
                            <button type="button" className="entropy-button entropy-button-primary" onClick={() => void saveRetention()} disabled={saving}>
                                {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Save size={15} />}
                                Save
                            </button>
                        </header>
                        <div className="settings-grid">
                            <Field label="Archive finished runs after (days)" hint={`Default ${retention.defaults.archive_after_days}.`}>
                                <input
                                    type="number"
                                    min={1}
                                    max={3650}
                                    value={retention.archive_after_days}
                                    onChange={(event) => update('retention', { archive_after_days: Number(event.target.value) })}
                                />
                            </Field>
                            <Field label="Delete archived runs after (days)" hint="0 keeps the archive forever.">
                                <input
                                    type="number"
                                    min={0}
                                    max={36500}
                                    value={retention.purge_archive_after_days}
                                    onChange={(event) => update('retention', { purge_archive_after_days: Number(event.target.value) })}
                                />
                            </Field>
                            <Field label="Delete notifications after (days)" hint="0 keeps them until people clear them.">
                                <input
                                    type="number"
                                    min={0}
                                    max={3650}
                                    value={retention.notifications_keep_days}
                                    onChange={(event) => update('retention', { notifications_keep_days: Number(event.target.value) })}
                                />
                            </Field>
                        </div>
                        <div className="settings-test">
                            <strong>Archive now</strong>
                            <span>
                                {retention.archived.jobs} runs and {retention.archived.events} events are in the archive.
                                Runs housekeeping with the saved settings.
                            </span>
                            <div>
                                <button type="button" className="entropy-button entropy-button-danger" onClick={() => void runRetention()} disabled={busy !== null}>
                                    {busy === 'retention' ? <LoaderCircle size={15} className="entropy-spin" /> : <Archive size={15} />}
                                    Archive and purge now
                                </button>
                            </div>
                        </div>
                    </>
                )}

                {tab === 'general' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>Address</h2>
                                <p>Where people open Entropy; used for links in e-mails.</p>
                            </div>
                            {saveButton('general')}
                        </header>
                        <div className="settings-grid">
                            <Field label="Public URL" hint={`For example ${window.location.origin}`} wide>
                                <input
                                    value={settings.general.public_url}
                                    onChange={(event) => update('general', { public_url: event.target.value })}
                                    placeholder={window.location.origin}
                                />
                            </Field>
                        </div>
                    </>
                )}
            </section>
        </div>
    )
}
