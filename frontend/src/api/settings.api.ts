import { apiRequest } from '../services/api'

export interface GroupMapping {
    /** Group name or DN at the directory / identity provider. */
    external: string
    /** Entropy group its members join. */
    group: string
}

export interface GeneralSettings {
    public_url: string
}

export interface SmtpSettings {
    enabled: boolean
    host: string
    port: number
    security: 'none' | 'starttls' | 'ssl'
    username: string
    /** Never sent back; empty means "unchanged" when saving. */
    password: string
    password_set: boolean
    from_address: string
    from_name: string
    verify_tls: boolean
}

export interface LdapSettings {
    enabled: boolean
    server_url: string
    start_tls: boolean
    verify_tls: boolean
    bind_dn: string
    bind_password: string
    bind_password_set: boolean
    user_base_dn: string
    user_filter: string
    attr_username: string
    attr_full_name: string
    attr_email: string
    auto_create_users: boolean
    group_attribute: string
    group_mappings: GroupMapping[]
}

export interface OidcSettings {
    enabled: boolean
    button_label: string
    issuer: string
    client_id: string
    client_secret: string
    client_secret_set: boolean
    scopes: string
    claim_username: string
    claim_full_name: string
    claim_email: string
    claim_groups: string
    auto_create_users: boolean
    group_mappings: GroupMapping[]
    verify_tls: boolean
}

export interface RetentionSettings {
    archive_after_days: number
    purge_archive_after_days: number
    notifications_keep_days: number
    archived: { jobs: number; events: number }
    defaults: { archive_after_days: number; purge_archive_after_days: number; notifications_keep_days: number }
}

/** Where a later migration would move Entropy's data; Entropy still runs on SQLite. */
export interface DatabaseTargetSettings {
    enabled: boolean
    engine: 'postgresql' | 'oracle'
    host: string
    port: number
    /** PostgreSQL database, or Oracle service name. */
    database: string
    schema: string
    username: string
    password: string
    password_set: boolean
    ssl: boolean
}

export interface CacheSettings {
    enabled: boolean
    host: string
    port: number
    database: number
    username: string
    password: string
    password_set: boolean
    tls: boolean
    verify_tls: boolean
    key_prefix: string
    default_ttl_seconds: number
}

export type Broker = 'activemq' | 'rabbitmq' | 'mqtt' | 'kafka'

export interface QueueSettings {
    enabled: boolean
    broker: Broker
    host: string
    port: number
    tls: boolean
    verify_tls: boolean
    username: string
    password: string
    password_set: boolean
    virtual_host: string
    client_id: string
    topic_prefix: string
}

export interface ConnectionTestResult {
    ok: boolean
    summary: string
    details: string[]
}

export interface AllSettings {
    general: GeneralSettings
    smtp: SmtpSettings
    ldap: LdapSettings
    oidc: OidcSettings
    database_target: DatabaseTargetSettings
    cache: CacheSettings
    queue: QueueSettings
    retention: RetentionSettings
}

export type SectionName = 'general' | 'smtp' | 'ldap' | 'oidc' | 'database_target' | 'cache' | 'queue'
export type ConnectionSection = 'database_target' | 'cache' | 'queue'

const json = (method: string, body: unknown): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
})

export const settingsApi = {
    all(): Promise<AllSettings> {
        return apiRequest('/api/admin/settings')
    },

    /** Secrets left empty keep their stored value; send null to keep, '' to clear. */
    save<T>(section: SectionName, values: Partial<T> | Record<string, unknown>): Promise<T> {
        return apiRequest(`/api/admin/settings/${section}`, json('PUT', values))
    },

    testMail(to: string | null): Promise<{ sent_to: string[] }> {
        return apiRequest('/api/admin/settings/smtp/test', json('POST', { to }))
    },

    testLdap(username: string, password: string): Promise<LdapTestResult> {
        return apiRequest('/api/admin/settings/ldap/test', json('POST', { username, password }))
    },

    testOidc(): Promise<{ issuer: string; authorization_endpoint: string; redirect_uri: string }> {
        return apiRequest('/api/admin/settings/oidc/test', json('POST', {}))
    },

    /** Checks the saved connection; rejects with the reason when it fails. */
    testConnection(section: ConnectionSection): Promise<ConnectionTestResult> {
        return apiRequest(`/api/admin/settings/connections/${section}/test`, json('POST', {}))
    },

    saveRetention(values: Partial<RetentionSettings>): Promise<RetentionSettings> {
        return apiRequest('/api/admin/settings/retention', json('PUT', values))
    },

    runRetention(): Promise<{ result: Record<string, number>; retention: RetentionSettings }> {
        return apiRequest('/api/admin/settings/retention/run', json('POST', {}))
    },
}

export interface LdapTestResult {
    found: boolean
    authenticated: boolean | null
    dn: string | null
    username: string | null
    full_name: string | null
    email: string | null
    groups: string[]
    mapped_groups: string[]
}

export interface RunAlertSettings {
    emails: string[]
    on_success: boolean
    on_failure: boolean
    on_cancel: boolean
    subject_template: string
    body_template: string
    updated_by?: string | null
    updated_at?: string | null
    /** E-mail is set up in Administration -> Settings. */
    mail_ready?: boolean
}

export const alertsApi = {
    get(kind: 'workflow' | 'schedule', target: string | number): Promise<RunAlertSettings> {
        const base = kind === 'workflow' ? 'workflows' : 'schedules'
        return apiRequest(`/api/${base}/${encodeURIComponent(String(target))}/alerts`)
    },

    save(
        kind: 'workflow' | 'schedule',
        target: string | number,
        values: RunAlertSettings,
    ): Promise<RunAlertSettings> {
        const base = kind === 'workflow' ? 'workflows' : 'schedules'
        return apiRequest(`/api/${base}/${encodeURIComponent(String(target))}/alerts`, json('PUT', values))
    },
}
