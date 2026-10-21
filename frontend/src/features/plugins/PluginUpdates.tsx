import { useCallback, useEffect, useState } from 'react'
import { ArrowUpCircle, LoaderCircle, PackagePlus, Sparkles } from 'lucide-react'

import { pluginsApi, type BundledUpdate } from '../../api/plugins.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'

function message(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

/**
 * Plugins shipped with this Entropy release that are not installed yet, or
 * newer than the installed version: a banner, and a dialog to pick what to
 * install. Nothing is installed without someone choosing it.
 */
export default function PluginUpdates({ onInstalled }: { onInstalled: () => void }) {
    const { notify } = useFeedback()
    const [items, setItems] = useState<BundledUpdate[]>([])
    const [canInstall, setCanInstall] = useState(false)
    const [open, setOpen] = useState(() => consumeCreateIntent('plugin-updates'))
    const [chosen, setChosen] = useState<Set<string>>(new Set())
    const [busy, setBusy] = useState(false)
    const [failures, setFailures] = useState<{ qualified_name: string; error: string }[]>([])

    const load = useCallback(async () => {
        try {
            const result = await pluginsApi.updates()
            setItems(result.items)
            setCanInstall(result.can_install)
            // Upgrades are picked by default; new plugins are opt-in.
            setChosen(new Set(result.items.filter((item) => item.kind === 'upgrade').map((item) => item.qualified_name)))
        } catch {
            setItems([])
        }
    }, [])

    useEffect(() => {
        Promise.resolve().then(load)
    }, [load])

    useCreateIntent('plugin-updates', () => setOpen(true))

    const upgrades = items.filter((item) => item.kind === 'upgrade')
    const fresh = items.filter((item) => item.kind === 'new')

    const toggle = (name: string) =>
        setChosen((current) => {
            const next = new Set(current)
            if (next.has(name)) next.delete(name)
            else next.add(name)
            return next
        })

    const install = async () => {
        setBusy(true)
        setFailures([])
        try {
            const result = await pluginsApi.installUpdates([...chosen])
            if (result.installed.length) {
                notify.success(
                    `${result.installed.length} plugin${result.installed.length === 1 ? '' : 's'} installed: ${result.installed
                        .map((plugin) => `${plugin.qualified_name} ${plugin.version}`)
                        .join(', ')}.`,
                )
                onInstalled()
            }
            setFailures(result.failed)
            await load()
            if (!result.failed.length) setOpen(false)
        } catch (cause) {
            notify.error(message(cause, 'Unable to install the plugins.'))
        } finally {
            setBusy(false)
        }
    }

    if (!items.length) return null

    const summary = [
        upgrades.length ? `${upgrades.length} upgrade${upgrades.length === 1 ? '' : 's'}` : '',
        fresh.length ? `${fresh.length} new plugin${fresh.length === 1 ? '' : 's'}` : '',
    ]
        .filter(Boolean)
        .join(' and ')

    const section = (title: string, list: BundledUpdate[]) =>
        list.length > 0 && (
            <section className="plugin-updates-group">
                <h3>{title}</h3>
                <ul>
                    {list.map((item) => (
                        <li key={item.qualified_name}>
                            <label>
                                <input
                                    type="checkbox"
                                    checked={chosen.has(item.qualified_name)}
                                    onChange={() => toggle(item.qualified_name)}
                                    disabled={!canInstall || busy}
                                />
                                <span className="plugin-updates-name">
                                    <strong>{item.display_name}</strong>
                                    <code>{item.qualified_name}</code>
                                    {item.description && <small>{item.description}</small>}
                                </span>
                                <span className={`plugin-updates-version is-${item.kind}`}>
                                    {item.kind === 'upgrade'
                                        ? `${item.installed_version} → ${item.available_version}`
                                        : item.available_version}
                                </span>
                            </label>
                        </li>
                    ))}
                </ul>
            </section>
        )

    return (
        <>
            <div className="plugin-updates-banner" role="status">
                <Sparkles size={17} aria-hidden="true" />
                <span>
                    This Entropy release brings <strong>{summary}</strong>.
                </span>
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setOpen(true)}>
                    Review
                </button>
            </div>

            {open && (
                <Dialog
                    title="Plugins in this release"
                    subtitle="Shipped with Entropy and not installed yet, or newer than yours. Upgrades keep the previous version in History."
                    icon={<PackagePlus size={18} />}
                    onClose={() => setOpen(false)}
                    className="plugin-updates-dialog"
                    footer={
                        <>
                            <button type="button" className="entropy-button entropy-button-secondary" onClick={() => setOpen(false)}>
                                Close
                            </button>
                            {canInstall && (
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-primary"
                                    onClick={() => void install()}
                                    disabled={busy || chosen.size === 0}
                                >
                                    {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <ArrowUpCircle size={15} />}
                                    Install {chosen.size || ''}
                                </button>
                            )}
                        </>
                    }
                >
                    {!canInstall && (
                        <p className="entropy-alert entropy-alert-warning" role="status">
                            Installing plugins needs the plugins.write permission; ask an administrator.
                        </p>
                    )}
                    <div className="plugin-updates-select">
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => setChosen(new Set(items.map((item) => item.qualified_name)))}
                            disabled={!canInstall || busy}
                        >
                            Select all
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => setChosen(new Set())}
                            disabled={!canInstall || busy}
                        >
                            Select none
                        </button>
                    </div>
                    {section('Upgrades', upgrades)}
                    {section('New plugins', fresh)}
                    {failures.length > 0 && (
                        <div className="entropy-alert entropy-alert-error" role="alert">
                            {failures.map((failure) => (
                                <p key={failure.qualified_name}>
                                    <strong>{failure.qualified_name}</strong>: {failure.error}
                                </p>
                            ))}
                        </div>
                    )}
                </Dialog>
            )}
        </>
    )
}
