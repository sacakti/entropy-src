import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, FolderKanban, Settings2 } from 'lucide-react'

import { apiRequest } from '../../services/api'
import {
    currentProject,
    setCurrentProject,
    PROJECT_CHANGED_EVENT,
    PROJECTS_UPDATED_EVENT,
} from '../../services/project'
import FloatingMenu from './FloatingMenu'

interface ProjectChoice {
    key: string
    name: string
    description: string
    my_roles: string[]
}

/**
 * The project the UI works in. Workflows, schedules, runs and drafts are
 * shown and created in it; the user's roles there decide what they may do.
 */
export default function ProjectSwitcher({ onManage }: { onManage?: () => void }) {
    const [projects, setProjects] = useState<ProjectChoice[]>([])
    const [active, setActive] = useState<string | null>(currentProject())
    const [open, setOpen] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)

    useEffect(() => {
        let alive = true
        const load = () =>
            apiRequest<{ items: ProjectChoice[]; current: string | null }>('/api/projects')
                .then((result) => {
                    if (!alive) return
                    setProjects(result.items)
                    // A project the user lost access to (or was deleted) is dropped.
                    const stored = currentProject()
                    if (stored && !result.items.some((item) => item.key === stored)) {
                        setCurrentProject(null)
                    }
                    setActive(currentProject() ?? result.current)
                })
                .catch(() => undefined)
        void load()
        const onChange = () => {
            setActive(currentProject())
            void load()
        }
        const onUpdated = () => void load()
        window.addEventListener(PROJECT_CHANGED_EVENT, onChange)
        window.addEventListener(PROJECTS_UPDATED_EVENT, onUpdated)
        return () => {
            alive = false
            window.removeEventListener(PROJECT_CHANGED_EVENT, onChange)
            window.removeEventListener(PROJECTS_UPDATED_EVENT, onUpdated)
        }
    }, [])

    const current = projects.find((item) => item.key === active)
    if (projects.length === 0) return null

    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                className="project-switcher"
                data-tour="project"
                onClick={() => setOpen((value) => !value)}
                aria-haspopup="menu"
                aria-expanded={open}
                title="Project: what you see and create here belongs to it"
            >
                <FolderKanban size={15} aria-hidden="true" />
                <span className="project-switcher-name">{current?.name ?? 'Project'}</span>
                <ChevronDown size={13} aria-hidden="true" />
            </button>
            <FloatingMenu
                anchorRef={triggerRef}
                open={open}
                onClose={() => setOpen(false)}
                align="start"
                className="project-switcher-menu"
            >
                <span className="topbar-create-label">Projects</span>
                {projects.map((project) => (
                    <button
                        key={project.key}
                        type="button"
                        role="menuitemradio"
                        aria-checked={project.key === active}
                        onClick={() => {
                            setOpen(false)
                            setCurrentProject(project.key)
                        }}
                    >
                        <span className="project-switcher-check" aria-hidden="true">
                            {project.key === active && <Check size={14} />}
                        </span>
                        <span className="project-switcher-item">
                            <strong>{project.name}</strong>
                            <small>
                                {project.my_roles.length > 0 ? project.my_roles.join(', ') : project.key}
                            </small>
                        </span>
                    </button>
                ))}
                {onManage && (
                    <>
                        <span className="project-switcher-divider" />
                        <button
                            type="button"
                            onClick={() => {
                                setOpen(false)
                                onManage()
                            }}
                        >
                            <span className="project-switcher-check" aria-hidden="true">
                                <Settings2 size={14} />
                            </span>
                            Manage projects
                        </button>
                    </>
                )}
            </FloatingMenu>
        </>
    )
}
