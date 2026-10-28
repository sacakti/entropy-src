import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
    Archive,
    CheckCircle2,
    Database,
    DatabaseZap,
    Globe,
    KeyRound,
    LoaderCircle,
    Mail,
    MessagesSquare,
    Plug,
    Plus,
    Save,
    Send,
    ShieldCheck,
    Trash2,
    Users,
    Zap,
} from 'lucide-react'

import {
    settingsApi,
    type AllSettings,
    type Broker,
    type ConnectionSection,
    type ConnectionTestResult,
    type DatabaseTargetSettings,
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

type Tab = 'general' | 'smtp' | 'ldap' | 'oidc' | 'retention' | 'database' | 'migration' | 'cache' | 'queue'

const TABS: { id: Tab; label: string; icon: typeof Mail; hint: string }[] = [
    { id: 'smtp', label: 'E-mail', icon: Mail, hint: 'SMTP server for alerts and messages' },
    { id: 'ldap', label: 'LDAP / Active Directory', icon: Users, hint: 'Sign in with directory accounts' },
    { id: 'oidc', label: 'Single sign-on', icon: KeyRound, hint: 'OpenID Connect (Keycloak, Azure AD, Okta)' },
    { id: 'retention', label: 'Data retention', icon: Archive, hint: 'Archive and purge old runs' },
    { id: 'database', label: 'Database', icon: Database, hint: 'Backups, checks and recovery' },
    { id: 'migration', label: 'Database migration', icon: DatabaseZap, hint: 'PostgreSQL or Oracle target' },
    { id: 'cache', label: 'Cache', icon: Zap, hint: 'Redis server' },
    { id: 'queue', label: 'Message queue', icon: MessagesSquare, hint: 'ActiveMQ, RabbitMQ, MQTT, Kafka' },
    { id: 'general', label: 'Address', icon: Globe, hint: 'Where people open Entropy' },
]

const ENGINE_PORTS: Record<DatabaseTargetSettings['engine'], number> = { postgresql: 5432, oracle: 1521 }
const BROKERS: { id: Broker; label: string; port: number; tlsPort: number; hint: string }[] = [
    { id: 'activemq', label: 'ActiveMQ (STOMP)', port: 61613, tlsPort: 61614, hint: 'STOMP connector, usually 61613 (61614 with TLS). OpenWire on 61616 is not used.' },
    { id: 'rabbitmq', label: 'RabbitMQ (AMQP 0-9-1)', port: 5672, tlsPort: 5671, hint: 'AMQP on 5672 (5671 with TLS).' },
    { id: 'mqtt', label: 'MQTT 3.1.1', port: 1883, tlsPort: 8883, hint: 'Mosquitto, HiveMQ, EMQX, or ActiveMQ/RabbitMQ with MQTT enabled: 1883 (8883 with TLS).' },
    { id: 'kafka', label: 'Apache Kafka', port: 9092, tlsPort: 9093, hint: 'A bootstrap broker, usually 9092.' },
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
/** "Test connection" for a saved connection section, with what was verified. */
function ConnectionTest({ section, label }: { section: ConnectionSection; label: string }) {
    const { notify } = useFeedback()
    const [busy, setBusy] = useState(false)
    const [result, setResult] = useState<ConnectionTestResult | null>(null)
    const test = async () => {
        setBusy(true)
        setResult(null)
        try {
            setResult(await settingsApi.testConnection(section))
        } catch (cause) {
            notify.error(message(cause, 'The connection test failed.'), { title: label })
        } finally {
            setBusy(false)
        }
    }
    return (
        <div className="settings-test">
            <strong>Test the connection</strong>
            <span>Uses the saved settings. Save first if you changed them.</span>
            <div>
                <button type="button" className="entropy-button entropy-button-secondary" onClick={() => void test()} disabled={busy}>
                    {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Plug size={15} />}
                    Test connection
                </button>
            </div>
            {result && (
                <div className="settings-connection-result" role="status">
                    <CheckCircle2 size={16} aria-hidden="true" />
                    <span>
                        <strong>{result.summary}</strong>
                        {result.details.map((detail) => <small key={detail}>{detail}</small>)}
                    </span>
                </div>
            )}
        </div>
    )
}

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
                        {id === 'migration' && settings.database_target.enabled && <span className="settings-on">On</span>}
                        {id === 'cache' && settings.cache.enabled && <span className="settings-on">On</span>}
                        {id === 'queue' && settings.queue.enabled && <span className="settings-on">On</span>}
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

                {tab === 'migration' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>Database migration</h2>
                                <p>
                                    The PostgreSQL or Oracle database Entropy's data would move to. Entropy keeps running on
                                    its SQLite database; saving these settings does not move or copy anything.
                                </p>
                            </div>
                            {saveButton('database_target')}
                        </header>
                        <div className="settings-grid">
                            <Toggle checked={settings.database_target.enabled} onChange={(enabled) => update('database_target', { enabled })}>
                                Migration target configured
                            </Toggle>
                            <Field label="Database">
                                <select
                                    className="entropy-select"
                                    value={settings.database_target.engine}
                                    onChange={(event) => {
                                        const engine = event.target.value as DatabaseTargetSettings['engine']
                                        update('database_target', { engine, port: ENGINE_PORTS[engine] })
                                    }}
                                >
                                    <option value="postgresql">PostgreSQL</option>
                                    <option value="oracle">Oracle</option>
                                </select>
                            </Field>
                            <Field label="Host">
                                <input value={settings.database_target.host} onChange={(event) => update('database_target', { host: event.target.value })} placeholder="db.example.com" />
                            </Field>
                            <Field label="Port">
                                <input type="number" min={1} max={65535} value={settings.database_target.port} onChange={(event) => update('database_target', { port: Number(event.target.value) })} />
                            </Field>
                            <Field label={settings.database_target.engine === 'oracle' ? 'Service name' : 'Database name'} hint={settings.database_target.engine === 'oracle' ? 'For example ORCLPDB1.' : 'For example entropy.'}>
                                <input value={settings.database_target.database} onChange={(event) => update('database_target', { database: event.target.value })} />
                            </Field>
                            <Field label="Schema" hint="Optional. PostgreSQL defaults to public; Oracle to the user's schema.">
                                <input value={settings.database_target.schema} onChange={(event) => update('database_target', { schema: event.target.value })} />
                            </Field>
                            <Field label="User name">
                                <input value={settings.database_target.username} autoComplete="off" onChange={(event) => update('database_target', { username: event.target.value })} />
                            </Field>
                            <SecretField
                                label="Password"
                                isSet={settings.database_target.password_set && secrets['database_target.password'] !== ''}
                                value={secretValue('database_target.password')}
                                onChange={(value) => setSecrets((current) => ({ ...current, 'database_target.password': value }))}
                                onClear={() => setSecrets((current) => ({ ...current, 'database_target.password': '' }))}
                            />
                            <Toggle checked={settings.database_target.ssl} onChange={(ssl) => update('database_target', { ssl })}>
                                {settings.database_target.engine === 'oracle' ? 'Use TCPS (TLS)' : 'Require TLS (sslmode=require)'}
                            </Toggle>
                        </div>
                        <ConnectionTest section="database_target" label="Database migration" />
                    </>
                )}
                {tab === 'cache' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>Cache</h2>
                                <p>A Redis server for caching. Stored and testable; Entropy does not use a cache yet.</p>
                            </div>
                            {saveButton('cache')}
                        </header>
                        <div className="settings-grid">
                            <Toggle checked={settings.cache.enabled} onChange={(enabled) => update('cache', { enabled })}>
                                Redis cache configured
                            </Toggle>
                            <Field label="Host">
                                <input value={settings.cache.host} onChange={(event) => update('cache', { host: event.target.value })} placeholder="redis.example.com" />
                            </Field>
                            <Field label="Port">
                                <input type="number" min={1} max={65535} value={settings.cache.port} onChange={(event) => update('cache', { port: Number(event.target.value) })} />
                            </Field>
                            <Field label="Database number" hint="0 to 15.">
                                <input type="number" min={0} max={15} value={settings.cache.database} onChange={(event) => update('cache', { database: Number(event.target.value) })} />
                            </Field>
                            <Field label="User name" hint="Redis 6 ACL user. Leave empty for the default user.">
                                <input value={settings.cache.username} autoComplete="off" onChange={(event) => update('cache', { username: event.target.value })} />
                            </Field>
                            <SecretField
                                label="Password"
                                isSet={settings.cache.password_set && secrets['cache.password'] !== ''}
                                value={secretValue('cache.password')}
                                onChange={(value) => setSecrets((current) => ({ ...current, 'cache.password': value }))}
                                onClear={() => setSecrets((current) => ({ ...current, 'cache.password': '' }))}
                            />
                            <Field label="Key prefix" hint="Keeps Entropy's keys apart on a shared server.">
                                <input value={settings.cache.key_prefix} onChange={(event) => update('cache', { key_prefix: event.target.value })} />
                            </Field>
                            <Field label="Default lifetime (seconds)" hint="0 keeps entries until they are replaced.">
                                <input type="number" min={0} value={settings.cache.default_ttl_seconds} onChange={(event) => update('cache', { default_ttl_seconds: Number(event.target.value) })} />
                            </Field>
                            <Toggle checked={settings.cache.tls} onChange={(tls) => update('cache', { tls })}>
                                Use TLS
                            </Toggle>
                            {settings.cache.tls && (
                                <Toggle checked={settings.cache.verify_tls} onChange={(verify_tls) => update('cache', { verify_tls })}>
                                    Verify the server's TLS certificate
                                </Toggle>
                            )}
                        </div>
                        <ConnectionTest section="cache" label="Cache" />
                    </>
                )}
                {tab === 'queue' && (
                    <>
                        <header className="settings-admin-head">
                            <div>
                                <h2>Message queue</h2>
                                <p>A message broker for events and work. Stored and testable; Entropy does not publish to it yet.</p>
                            </div>
                            {saveButton('queue')}
                        </header>
                        <div className="settings-grid">
                            <Toggle checked={settings.queue.enabled} onChange={(enabled) => update('queue', { enabled })}>
                                Message queue configured
                            </Toggle>
                            <Field label="Broker" hint={BROKERS.find((broker) => broker.id === settings.queue.broker)?.hint}>
                                <select
                                    className="entropy-select"
                                    value={settings.queue.broker}
                                    onChange={(event) => {
                                        const broker = BROKERS.find((item) => item.id === event.target.value) ?? BROKERS[0]
                                        update('queue', { broker: broker.id, port: settings.queue.tls ? broker.tlsPort : broker.port })
                                    }}
                                >
                                    {BROKERS.map((broker) => <option key={broker.id} value={broker.id}>{broker.label}</option>)}
                                </select>
                            </Field>
                            <Field label="Host">
                                <input value={settings.queue.host} onChange={(event) => update('queue', { host: event.target.value })} placeholder="broker.example.com" />
                            </Field>
                            <Field label="Port">
                                <input type="number" min={1} max={65535} value={settings.queue.port} onChange={(event) => update('queue', { port: Number(event.target.value) })} />
                            </Field>
                            <Field label="User name" hint="Leave empty when the broker needs no sign-in.">
                                <input value={settings.queue.username} autoComplete="off" onChange={(event) => update('queue', { username: event.target.value })} />
                            </Field>
                            <SecretField
                                label="Password"
                                isSet={settings.queue.password_set && secrets['queue.password'] !== ''}
                                value={secretValue('queue.password')}
                                onChange={(value) => setSecrets((current) => ({ ...current, 'queue.password': value }))}
                                onClear={() => setSecrets((current) => ({ ...current, 'queue.password': '' }))}
                            />
                            {(settings.queue.broker === 'rabbitmq' || settings.queue.broker === 'activemq') && (
                                <Field label={settings.queue.broker === 'rabbitmq' ? 'Virtual host' : 'STOMP host header'} hint={settings.queue.broker === 'rabbitmq' ? 'Usually /.' : 'Usually / or the broker name.'}>
                                    <input value={settings.queue.virtual_host} onChange={(event) => update('queue', { virtual_host: event.target.value })} />
                                </Field>
                            )}
                            <Field label="Client ID" hint="How Entropy names itself to the broker.">
                                <input value={settings.queue.client_id} onChange={(event) => update('queue', { client_id: event.target.value })} />
                            </Field>
                            <Field label="Topic prefix" hint="Topics or queues would be named <prefix>.runs, <prefix>.releases and so on.">
                                <input value={settings.queue.topic_prefix} onChange={(event) => update('queue', { topic_prefix: event.target.value })} />
                            </Field>
                            <Toggle
                                checked={settings.queue.tls}
                                onChange={(tls) => {
                                    const broker = BROKERS.find((item) => item.id === settings.queue.broker)
                                    // Move between the usual plain and TLS ports, unless a custom port is set.
                                    const port = broker && settings.queue.port === (tls ? broker.port : broker.tlsPort) ? (tls ? broker.tlsPort : broker.port) : settings.queue.port
                                    update('queue', { tls, port })
                                }}
                            >
                                Use TLS
                            </Toggle>
                            {settings.queue.tls && (
                                <Toggle checked={settings.queue.verify_tls} onChange={(verify_tls) => update('queue', { verify_tls })}>
                                    Verify the broker's TLS certificate
                                </Toggle>
                            )}
                        </div>
                        <ConnectionTest section="queue" label="Message queue" />
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
