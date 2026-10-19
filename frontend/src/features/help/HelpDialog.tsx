import { useState } from 'react'
import { Check, Copy, HelpCircle, Keyboard, Terminal } from 'lucide-react'

import Dialog from '../../components/layout/Dialog'
import { CLI_GROUPS, SHORTCUT_GROUPS } from './helpContent'

type Tab = 'shortcuts' | 'cli'

export default function HelpDialog({ onClose }: { onClose: () => void }) {
    const [tab, setTab] = useState<Tab>('shortcuts')
    const [copied, setCopied] = useState<string | null>(null)

    const copy = async (command: string) => {
        try {
            await navigator.clipboard.writeText(command)
            setCopied(command)
            window.setTimeout(() => setCopied((value) => (value === command ? null : value)), 1500)
        } catch {
            setCopied(null)
        }
    }

    return (
        <Dialog
            title="Help"
            subtitle="Keyboard shortcuts and Entropy CLI commands."
            icon={<HelpCircle size={18} />}
            onClose={onClose}
            className="help-dialog"
        >
            <div className="help-tabs" role="tablist">
                <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'shortcuts'}
                    className={tab === 'shortcuts' ? 'is-active' : ''}
                    onClick={() => setTab('shortcuts')}
                >
                    <Keyboard size={15} />
                    Keyboard shortcuts
                </button>
                <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'cli'}
                    className={tab === 'cli' ? 'is-active' : ''}
                    onClick={() => setTab('cli')}
                >
                    <Terminal size={15} />
                    Entropy CLI
                </button>
            </div>

            {tab === 'shortcuts' ? (
                <div className="help-groups">
                    {SHORTCUT_GROUPS.map((group) => (
                        <section key={group.title} className="help-group">
                            <h3>{group.title}</h3>
                            <dl>
                                {group.entries.map((entry) => (
                                    <div key={entry.action}>
                                        <dt>
                                            {entry.keys.map((key) => (
                                                <kbd key={key}>{key}</kbd>
                                            ))}
                                        </dt>
                                        <dd>{entry.action}</dd>
                                    </div>
                                ))}
                            </dl>
                            {group.note && <p className="help-note">{group.note}</p>}
                        </section>
                    ))}
                    <p className="help-note">On macOS use ⌘ in place of Ctrl.</p>
                </div>
            ) : (
                <div className="help-groups">
                    {CLI_GROUPS.map((group) => (
                        <section key={group.title} className="help-group">
                            <h3>{group.title}</h3>
                            <ul className="help-commands">
                                {group.commands.map((item) => (
                                    <li key={item.command}>
                                        <code>{item.command}</code>
                                        <span>{item.description}</span>
                                        <button
                                            type="button"
                                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                            aria-label={`Copy ${item.command}`}
                                            title="Copy"
                                            onClick={() => void copy(item.command)}
                                        >
                                            {copied === item.command ? <Check size={14} /> : <Copy size={14} />}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ))}
                    <p className="help-note">
                        Run <code>ent &lt;command&gt; -h</code> for every option.
                    </p>
                </div>
            )}
        </Dialog>
    )
}
