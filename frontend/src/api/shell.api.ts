import { apiRequest } from '../services/api'

export interface ShellInfo {
    commands: { command: string; description: string }[]
    /** First words the shell understands, for completion. */
    vocabulary: string[]
    timeout_seconds: number
}

export interface ShellResult {
    exit_code: number
    stdout: string
    stderr: string
}

export function getShellInfo(): Promise<ShellInfo> {
    return apiRequest<ShellInfo>('/api/shell')
}

/** Run one `ent` command (without the `ent`) as the signed-in user. */
export function runShellCommand(command: string): Promise<ShellResult> {
    return apiRequest<ShellResult>('/api/shell/exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
    })
}
