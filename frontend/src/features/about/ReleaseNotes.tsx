import { useEffect, useState } from 'react'
import { Bug, Gauge, ShieldCheck, Sparkles, type LucideIcon } from 'lucide-react'

import { getReleaseNotes, markReleaseNotesSeen, type ReleaseNote } from '../../api/version'
import Dialog from '../../components/layout/Dialog'
import '../../styles/release-notes.css'

const SECTION_ICONS: Record<string, LucideIcon> = {
    Security: ShieldCheck,
    New: Sparkles,
    Improved: Gauge,
    Fixed: Bug,
}

function formatDate(value: string | null): string {
    if (!value) return ''
    const date = new Date(`${value}T12:00:00`)
    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

function ReleaseBody({ release }: { release: ReleaseNote }) {
    return (
        <>
            {release.sections.map((section) => {
                const Icon = SECTION_ICONS[section.title] ?? Sparkles
                return (
                    <section key={section.title} className={`release-note-section is-${section.title.toLowerCase()}`}>
                        <h4>
                            <Icon size={13} aria-hidden="true" /> {section.title}
                        </h4>
                        <ul>
                            {section.items.map((item) => (
                                <li key={item}>{item}</li>
                            ))}
                        </ul>
                    </section>
                )
            })}
            {release.more ? (
                <p className="release-note-more">
                    and {release.more} more {release.more === 1 ? 'change' : 'changes'}
                </p>
            ) : null}
        </>
    )
}

/** Every release, newest first and open, the others a click away: for the About page. */
export function ReleaseHistory() {
    const [releases, setReleases] = useState<ReleaseNote[] | null>(null)

    useEffect(() => {
        let active = true
        getReleaseNotes()
            .then((notes) => {
                if (active) setReleases(notes.releases)
            })
            .catch(() => {
                if (active) setReleases([])
            })
        return () => {
            active = false
        }
    }, [])

    if (!releases?.length) return null

    return (
        <div className="release-history">
            <h3>Release notes</h3>
            {releases.map((release, index) => (
                <details key={release.version} open={index === 0}>
                    <summary>
                        <strong>Version {release.version}</strong>
                        <time>{formatDate(release.date)}</time>
                    </summary>
                    <ReleaseBody release={release} />
                </details>
            ))}
        </div>
    )
}

/** Once after an upgrade: what changed since this person last looked. */
export function WhatsNew({ onSeeAll }: { onSeeAll: () => void }) {
    const [unseen, setUnseen] = useState<ReleaseNote[]>([])

    useEffect(() => {
        let active = true
        getReleaseNotes()
            .then((notes) => {
                if (active) setUnseen(notes.unseen)
            })
            // Older servers lack this, and it is never worth an error.
            .catch(() => undefined)
        return () => {
            active = false
        }
    }, [])

    if (unseen.length === 0) return null

    const close = () => {
        setUnseen([])
        void markReleaseNotesSeen().catch(() => undefined)
    }

    return (
        <Dialog
            title={`What's new in ${unseen[0].version}`}
            subtitle={unseen.length > 1 ? `Also includes the ${unseen.length - 1} earlier version(s) you have not seen.` : formatDate(unseen[0].date)}
            icon={<Sparkles size={18} />}
            onClose={close}
            className="whats-new-dialog"
            footer={
                <>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => {
                            close()
                            onSeeAll()
                        }}
                    >
                        All release notes
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" onClick={close}>
                        Got it
                    </button>
                </>
            }
        >
            <div className="whats-new-body">
                {unseen.map((release, index) => (
                    <div key={release.version}>
                        {index > 0 && <h3>Version {release.version}</h3>}
                        <ReleaseBody release={release} />
                    </div>
                ))}
            </div>
        </Dialog>
    )
}
