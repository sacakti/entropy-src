import { useEffect, useState } from 'react'
import { Check, Copy, KeyRound } from 'lucide-react'

import { getCliInfo, issueCliToken, type CliInfo } from '../../api/cli.api'
import type { CliGroup } from './helpContent'

const REMOTE_GROUPS: CliGroup[] = [
    {
        title: 'Sessions and contexts',
        commands: [
            { command: 'ent whoami', description: 'Show the signed-in user and server.' },
            { command: 'ent status', description: 'Show the current context and session.' },
            { command: 'ent context list', description: 'List the servers you are logged in to.' },
            { command: 'ent context use <name>', description: 'Switch to another server.' },
            { command: 'ent logout', description: 'Revoke the token and log out.' },
        ],
    },
    {
        title: 'Workflows and jobs',
        commands: [
            { command: 'ent workflow list', description: 'List workflows.' },
            { command: 'ent workflow get <name> -o yaml', description: 'Show a workflow definition.' },
            { command: 'ent workflow apply -f <file>', description: 'Create or update a workflow.' },
            { command: 'ent workflow run <name> --follow', description: 'Run a workflow and follow its log.' },
            { command: 'ent job list', description: 'List runs.' },
            { command: 'ent job logs <id> -f', description: 'Follow a run log.' },
            { command: 'ent job stop <id>', description: 'Stop a run.' },
        ],
    },
    {
        title: 'Other',
        commands: [
            { command: 'ent plugin list', description: 'List plugins.' },
            { command: 'ent node list', description: 'List nodes.' },
            { command: 'ent schedule list', description: 'List schedules.' },
        ],
    },
]

/** The `ent` command line for other computers: install, log in, commands. */
export default function RemoteCliPanel({
    copied,
    onCopy,
}: {
    copied: string | null
    onCopy: (command: string) => void
}) {
    const [info, setInfo] = useState<CliInfo | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [tokenLogin, setTokenLogin] = useState<string | null>(null)
    const [issuing, setIssuing] = useState(false)

    useEffect(() => {
        getCliInfo()
            .then(setInfo)
            .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
    }, [])

    const issueToken = async () => {
        setIssuing(true)
        setError(null)
        try {
            const { token } = await issueCliToken()
            const command = `ent login ${info?.server ?? window.location.origin} --token ${token}`
            setTokenLogin(command)
            onCopy(command)
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : String(reason))
        } finally {
            setIssuing(false)
        }
    }

    const row = (command: string, description: string) => (
        <li key={command}>
            <code>{command}</code>
            <span>{description}</span>
            <button
                type="button"
                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                aria-label={`Copy ${command}`}
                title="Copy"
                onClick={() => onCopy(command)}
            >
                {copied === command ? <Check size={14} /> : <Copy size={14} />}
            </button>
        </li>
    )

    return (
        <div className="help-groups">
            <p className="help-note">
                Use Entropy from any computer or node, like <code>oc</code> with a cluster URL: install{' '}
                <code>ent</code>, then log in to this server. {info && `Requires ${info.requires}.`}
            </p>
            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <span>{error}</span>
                </div>
            )}
            {info && (
                <>
                    <section className="help-group">
                        <h3>Install (version {info.version})</h3>
                        <ul className="help-commands">
                            {row(info.install.posix, 'Linux and macOS.')}
                            {row(info.install.windows, 'Windows PowerShell.')}
                        </ul>
                    </section>
                    <section className="help-group">
                        <h3>Log in</h3>
                        <ul className="help-commands">
                            {row(info.login, 'Prompts for your user name and password.')}
                            {tokenLogin && row(tokenLogin, 'Logs in as you without a password. Keep it secret.')}
                        </ul>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm help-token-button"
                            onClick={() => void issueToken()}
                            disabled={issuing}
                        >
                            <KeyRound size={14} />
                            {tokenLogin ? 'Copy a new login command' : 'Copy login command with a token'}
                        </button>
                    </section>
                </>
            )}
            {REMOTE_GROUPS.map((group) => (
                <section key={group.title} className="help-group">
                    <h3>{group.title}</h3>
                    <ul className="help-commands">
                        {group.commands.map((item) => row(item.command, item.description))}
                    </ul>
                </section>
            ))}
            <p className="help-note">
                Run <code>ent &lt;command&gt; -h</code> for every option. Nodes set up with &quot;Install the
                ent command line&quot; already have it, pointed at this server.
            </p>
        </div>
    )
}
