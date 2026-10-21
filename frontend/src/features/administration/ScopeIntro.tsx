import { FolderKanban, Globe } from 'lucide-react'

/** One-line explanation of global and project roles, shown atop Roles and Projects. */
export default function ScopeIntro() {
    return (
        <div className="admin-scope-intro">
            <div>
                <span className="admin-scope-icon" aria-hidden="true">
                    <Globe size={16} />
                </span>
                <p>
                    <strong>Global roles</strong> apply everywhere and are given straight to users and groups — for
                    example, managing users, nodes or plugins.
                </p>
            </div>
            <div>
                <span className="admin-scope-icon" aria-hidden="true">
                    <FolderKanban size={16} />
                </span>
                <p>
                    <strong>Project roles</strong> are given to people inside a project and only cover that project’s
                    workflows, schedules, drafts and runs.
                </p>
            </div>
        </div>
    )
}
