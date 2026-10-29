import { apiRequest } from '../services/api'

/** One resource of the command contract shared with the `ent` client. */
export interface ShellResource {
    help: string
    aliases: string[]
    verbs: Record<string, { help: string; aliases: string[] }>
}

export interface ShellInfo {
    commands: { command: string; description: string }[]
    /** First words the shell understands, for completion. */
    vocabulary: string[]
    resources: Record<string, ShellResource>
    output_modes: string[]
    timeout_seconds: number
}

export interface ShellResult {
    exit_code: number
    stdout: string
    stderr: string
    /** Page settings a command changed (`project set`, `config set output`). */
    effects?: { project?: string | null; output?: string | null }
}

export function getShellInfo(): Promise<ShellInfo> {
    return apiRequest<ShellInfo>('/api/shell')
}

/**
 * Run one `ent` command (without the `ent`) as the signed-in user, in the
 * page's current project and with the saved output mode.
 */
export function runShellCommand(command: string, output: string | null): Promise<ShellResult> {
    return apiRequest<ShellResult>('/api/shell/exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, output }),
    })
}
