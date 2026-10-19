/** Reference shown in the Help dialog. Keep in sync with page shortcuts. */

export interface ShortcutEntry {
    keys: string[]
    action: string
}

export interface ShortcutGroup {
    title: string
    note?: string
    entries: ShortcutEntry[]
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
    {
        title: 'Anywhere',
        entries: [
            { keys: ['?'], action: 'Open this help' },
            { keys: ['Alt', '←'], action: 'Back to the previous page (browser back)' },
            { keys: ['Alt', '→'], action: 'Forward (browser forward)' },
            { keys: ['Esc'], action: 'Close a menu, dialog or viewer' },
        ],
    },
    {
        title: 'Plugins',
        note: 'Chrome reserves Ctrl+N for a new window; use Alt+N there.',
        entries: [
            { keys: ['Ctrl', 'N'], action: 'Create a plugin (also Alt+N)' },
            { keys: ['Ctrl', 'S'], action: 'In the editor: review changes, then save' },
            { keys: ['Ctrl', 'F'], action: 'Search plugins; find text in the editor' },
            { keys: ['Ctrl', 'D'], action: 'Delete the selected plugin, or choose one' },
        ],
    },
    {
        title: 'Workflows',
        entries: [
            { keys: ['Ctrl', 'N'], action: 'Create a workflow (also Alt+N)' },
            { keys: ['Ctrl', 'S'], action: 'In the builder: review changes, then save' },
            { keys: ['Ctrl', 'F'], action: 'Search workflows; find text in JSON/YAML view' },
            { keys: ['Ctrl', 'D'], action: 'Delete the selected workflow, or choose one' },
        ],
    },
    {
        title: 'Vault',
        entries: [
            { keys: ['Ctrl', 'N'], action: 'Create a vault entry (also Alt+N)' },
            { keys: ['Ctrl', 'Shift', 'S'], action: 'Create a namespace' },
            { keys: ['Ctrl', 'D'], action: 'Delete the selected entry, or choose one' },
            { keys: ['Ctrl', 'Shift', 'D'], action: 'Delete the current namespace' },
        ],
    },
    {
        title: 'Administration (users, groups, roles)',
        entries: [
            { keys: ['Ctrl', 'N'], action: 'Create a user, group or role (also Alt+N)' },
            { keys: ['Ctrl', 'F'], action: 'Search the list' },
        ],
    },
    {
        title: 'Wallpaper viewer',
        entries: [
            { keys: ['←', '→'], action: 'Previous / next wallpaper' },
            { keys: ['F'], action: 'Maximize / restore' },
            { keys: ['+', '−'], action: 'Zoom in / out' },
            { keys: ['0'], action: 'Fit to screen' },
        ],
    },
]

export interface CliCommand {
    command: string
    description: string
}

export interface CliGroup {
    title: string
    commands: CliCommand[]
}

export const CLI_GROUPS: CliGroup[] = [
    {
        title: 'Sessions',
        commands: [
            { command: 'ent auth login', description: 'Authenticate.' },
            { command: 'ent auth status', description: 'Display the current session.' },
            { command: 'ent auth switch -u <username>', description: 'Switch to an authenticated user.' },
            { command: 'ent auth logout', description: 'Log out the current session.' },
        ],
    },
    {
        title: 'Plugins',
        commands: [
            { command: 'ent plugin list', description: 'List installed plugins.' },
            { command: 'ent plugin install <directory>', description: 'Install a plugin.' },
            { command: 'ent plugin run <namespace.name> -a KEY=VALUE', description: 'Execute a plugin.' },
            { command: 'ent plugin set --enable|--disable <plugin>', description: 'Enable or disable a plugin.' },
            { command: 'ent plugin verify <plugin>', description: 'Verify an installed plugin.' },
            { command: 'ent plugin upgrade', description: 'Check and upgrade plugins.' },
            { command: 'ent plugin man <plugin>', description: 'Read plugin documentation.' },
            { command: 'ent generate plugin -n <namespace> <name>', description: 'Generate a new plugin.' },
        ],
    },
    {
        title: 'Workflows',
        commands: [
            { command: 'ent workflow list', description: 'List registered workflows.' },
            { command: 'ent workflow add <file>', description: 'Register a workflow.' },
            { command: 'ent workflow show <name> --yaml', description: 'Show a registered workflow.' },
            { command: 'ent workflow run <name>', description: 'Run a workflow in the foreground.' },
            { command: 'ent workflow start <name>', description: 'Start a workflow in the background.' },
            { command: 'ent workflow jobs', description: 'List workflow jobs.' },
            { command: 'ent workflow follow --pid <pid>', description: 'Follow a running workflow.' },
            { command: 'ent workflow stop --pid <pid> | --name <name>', description: 'Stop workflow processes.' },
        ],
    },
    {
        title: 'Vault',
        commands: [
            { command: 'ent vault list -n <namespace>', description: 'List vault entries.' },
            { command: 'ent vault add -n <namespace> <key> <value>', description: 'Add a vault entry.' },
            { command: 'ent vault inspect -n <namespace> <key> --reveal', description: 'Inspect a vault entry.' },
            { command: 'ent vault namespace list', description: 'List vault namespaces.' },
            { command: 'ent vault namespace users', description: 'Manage namespace users.' },
        ],
    },
    {
        title: 'Administration',
        commands: [
            { command: 'ent user list', description: 'List users.' },
            { command: 'ent user create', description: 'Create a user.' },
            { command: 'ent user password', description: 'Manage user passwords.' },
            { command: 'ent groups list', description: 'List groups.' },
            { command: 'ent roles list', description: 'List roles.' },
            { command: 'ent migrate', description: 'Apply database migrations.' },
            { command: 'ent version', description: 'Show the Entropy version.' },
        ],
    },
]
