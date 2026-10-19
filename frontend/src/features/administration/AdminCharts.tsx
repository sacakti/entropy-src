import { useState, type PointerEvent, type ReactNode } from 'react'

import type { AdminSummary } from '../../api/admin.api'

/*
 * Small HTML bar charts for the Administration overview. Bars are plain
 * elements so they follow the theme tokens; every value is also printed,
 * and each chart has a table view.
 */

interface Tip {
    x: number
    y: number
    content: ReactNode
}

function ChartCard({
    title,
    subtitle,
    legend,
    table,
    children,
}: {
    title: string
    subtitle: string
    legend?: ReactNode
    table: ReactNode
    children: (setTip: (tip: Tip | null) => void) => ReactNode
}) {
    const [tip, setTip] = useState<Tip | null>(null)
    const [showTable, setShowTable] = useState(false)

    return (
        <section className="admin-chart" onPointerLeave={() => setTip(null)}>
            <header>
                <div>
                    <h3>{title}</h3>
                    <p>{subtitle}</p>
                </div>
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-sm"
                    onClick={() => setShowTable((value) => !value)}
                    aria-pressed={showTable}
                >
                    {showTable ? 'Chart' : 'Table'}
                </button>
            </header>
            {legend && !showTable && <div className="admin-chart-legend">{legend}</div>}
            {showTable ? <div className="admin-chart-table">{table}</div> : children(setTip)}
            {tip && (
                <div className="admin-chart-tip" style={{ left: tip.x, top: tip.y }} role="status">
                    {tip.content}
                </div>
            )}
        </section>
    )
}

/** Position a tooltip relative to the chart card. */
function tipAt(event: PointerEvent<HTMLElement>, content: ReactNode): Tip {
    const card = event.currentTarget.closest('.admin-chart')?.getBoundingClientRect()

    return {
        x: event.clientX - (card?.left ?? 0) + 12,
        y: event.clientY - (card?.top ?? 0) + 12,
        content,
    }
}

function Empty({ text }: { text: string }) {
    return <p className="admin-chart-empty">{text}</p>
}

function BarList({
    rows,
    setTip,
    unit,
}: {
    rows: { label: string; value: number; detail?: string }[]
    setTip: (tip: Tip | null) => void
    unit: string
}) {
    const max = Math.max(1, ...rows.map((row) => row.value))

    return (
        <ul className="admin-bars">
            {rows.map((row) => (
                <li
                    key={row.label}
                    onPointerMove={(event) =>
                        setTip(
                            tipAt(
                                event,
                                <>
                                    <strong>{row.label}</strong>
                                    <span>
                                        {row.value} {unit}
                                    </span>
                                    {row.detail && <span>{row.detail}</span>}
                                </>,
                            ),
                        )
                    }
                >
                    <span className="admin-bars-label" title={row.label}>
                        {row.label}
                    </span>
                    <span className="admin-bars-track">
                        <span
                            className="admin-bars-fill"
                            style={{ width: `${(row.value / max) * 100}%` }}
                        />
                    </span>
                    <span className="admin-bars-value">{row.value}</span>
                </li>
            ))}
        </ul>
    )
}

const TYPES = [
    { key: 'read', label: 'Read' },
    { key: 'write', label: 'Write' },
    { key: 'execute', label: 'Execute' },
] as const

export default function AdminCharts({ summary }: { summary: AdminSummary }) {
    const { groups, roles, modules } = summary.charts
    const disabled = summary.users - summary.active_users
    const moduleMax = Math.max(1, ...modules.map((module) => module.read + module.write + module.execute))

    return (
        <div className="admin-charts">
            <ChartCard
                title="Users"
                subtitle="Accounts that can and cannot sign in."
                legend={
                    <>
                        <span className="admin-key is-series-1">Active</span>
                        <span className="admin-key is-neutral">Disabled</span>
                    </>
                }
                table={
                    <table>
                        <tbody>
                            <tr><th>Active</th><td>{summary.active_users}</td></tr>
                            <tr><th>Disabled</th><td>{disabled}</td></tr>
                            <tr><th>Total</th><td>{summary.users}</td></tr>
                        </tbody>
                    </table>
                }
            >
                {(setTip) => (
                    <div className="admin-users-chart">
                        <div className="admin-hero">
                            <strong>{summary.active_users}</strong>
                            <span>of {summary.users} active</span>
                        </div>
                        <div className="admin-split" aria-hidden="true">
                            {[
                                { label: 'Active', value: summary.active_users, tone: 'is-series-1' },
                                { label: 'Disabled', value: disabled, tone: 'is-neutral' },
                            ]
                                .filter((part) => part.value > 0)
                                .map((part) => (
                                    <span
                                        key={part.label}
                                        className={part.tone}
                                        style={{ flexGrow: part.value }}
                                        onPointerMove={(event) =>
                                            setTip(
                                                tipAt(
                                                    event,
                                                    <>
                                                        <strong>{part.label}</strong>
                                                        <span>
                                                            {part.value} of {summary.users} users
                                                        </span>
                                                    </>,
                                                ),
                                            )
                                        }
                                    />
                                ))}
                        </div>
                    </div>
                )}
            </ChartCard>

            <ChartCard
                title="Groups"
                subtitle={groups.length ? 'Members per group (largest first).' : 'No groups yet.'}
                table={
                    <table>
                        <thead><tr><th>Group</th><th>Members</th></tr></thead>
                        <tbody>
                            {groups.map((group) => (
                                <tr key={group.name}><th>{group.name}</th><td>{group.members}</td></tr>
                            ))}
                        </tbody>
                    </table>
                }
            >
                {(setTip) =>
                    groups.length ? (
                        <BarList
                            rows={groups.map((group) => ({ label: group.name, value: group.members }))}
                            setTip={setTip}
                            unit="members"
                        />
                    ) : (
                        <Empty text="Create a group to give several users the same roles." />
                    )
                }
            </ChartCard>

            <ChartCard
                title="Roles"
                subtitle="Permissions per role, most-assigned roles first."
                table={
                    <table>
                        <thead><tr><th>Role</th><th>Permissions</th><th>Users</th><th>Groups</th></tr></thead>
                        <tbody>
                            {roles.map((role) => (
                                <tr key={role.name}>
                                    <th>{role.name}</th><td>{role.permissions}</td><td>{role.users}</td><td>{role.groups}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                }
            >
                {(setTip) => (
                    <BarList
                        rows={roles.map((role) => ({
                            label: role.name,
                            value: role.permissions,
                            detail: `${role.users} user${role.users === 1 ? '' : 's'} · ${role.groups} group${
                                role.groups === 1 ? '' : 's'
                            }`,
                        }))}
                        setTip={setTip}
                        unit="permissions"
                    />
                )}
            </ChartCard>

            <ChartCard
                title="Permissions"
                subtitle="Permissions per module by type."
                legend={TYPES.map((type, index) => (
                    <span key={type.key} className={`admin-key is-series-${index + 1}`}>
                        {type.label}
                    </span>
                ))}
                table={
                    <table>
                        <thead><tr><th>Module</th><th>Read</th><th>Write</th><th>Execute</th></tr></thead>
                        <tbody>
                            {modules.map((module) => (
                                <tr key={module.name}>
                                    <th>{module.name}</th><td>{module.read}</td><td>{module.write}</td><td>{module.execute}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                }
            >
                {(setTip) => (
                    <ul className="admin-bars">
                        {modules.map((module) => {
                            const total = module.read + module.write + module.execute

                            return (
                                <li
                                    key={module.name}
                                    onPointerMove={(event) =>
                                        setTip(
                                            tipAt(
                                                event,
                                                <>
                                                    <strong>{module.name}</strong>
                                                    {TYPES.map((type) => (
                                                        <span key={type.key}>
                                                            {type.label}: {module[type.key]}
                                                        </span>
                                                    ))}
                                                </>,
                                            ),
                                        )
                                    }
                                >
                                    <span className="admin-bars-label">{module.name}</span>
                                    <span className="admin-bars-track">
                                        <span className="admin-stack" style={{ width: `${(total / moduleMax) * 100}%` }}>
                                            {TYPES.map((type, index) =>
                                                module[type.key] > 0 ? (
                                                    <span
                                                        key={type.key}
                                                        className={`is-series-${index + 1}`}
                                                        style={{ flexGrow: module[type.key] }}
                                                    />
                                                ) : null,
                                            )}
                                        </span>
                                    </span>
                                    <span className="admin-bars-value">{total}</span>
                                </li>
                            )
                        })}
                    </ul>
                )}
            </ChartCard>
        </div>
    )
}
