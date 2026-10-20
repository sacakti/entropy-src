import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

import type { Profile } from '../../api/profile.api'

/** Initials for a display name, falling back to the username's first letter. */
function initials(profile: Pick<Profile, 'username' | 'full_name'>): string {
    const words = (profile.full_name ?? '').trim().split(/\s+/).filter(Boolean)

    if (words.length >= 2) return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase()
    if (words.length === 1) return words[0][0].toUpperCase()

    return profile.username.charAt(0).toUpperCase()
}

/** The profile picture at full size over the page; click or Esc closes it. */
function AvatarPreview({ src, name, onClose }: { src: string; name: string; onClose: () => void }) {
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation()
                onClose()
            }
        }
        window.addEventListener('keydown', onKey, true)
        return () => window.removeEventListener('keydown', onKey, true)
    }, [onClose])

    return createPortal(
        <div
            className="avatar-preview"
            role="dialog"
            aria-modal="true"
            aria-label={`Profile picture of ${name}`}
            onClick={onClose}
        >
            <img src={src} alt={`Profile picture of ${name}`} onClick={(event) => event.stopPropagation()} />
            <button
                type="button"
                className="avatar-preview-close"
                aria-label="Close"
                onClick={onClose}
                autoFocus
            >
                <X size={18} />
            </button>
        </div>,
        document.body,
    )
}

/**
 * Profile picture, or initials on an accent tile when none is set. With
 * `zoomable`, clicking a picture shows it full size.
 */
export default function Avatar({
    profile,
    size = 30,
    className,
    zoomable = false,
}: {
    profile: Pick<Profile, 'username' | 'full_name' | 'avatar_url'>
    size?: number
    className?: string
    zoomable?: boolean
}) {
    const [previewing, setPreviewing] = useState(false)
    const style = { width: size, height: size, fontSize: Math.round(size * 0.4) }
    const classes = ['entropy-avatar', className].filter(Boolean)

    if (zoomable && profile.avatar_url) {
        const name = profile.full_name || profile.username
        return (
            <>
                <button
                    type="button"
                    className={[...classes, 'is-zoomable'].join(' ')}
                    style={style}
                    title="Show picture"
                    aria-label="Show profile picture"
                    onClick={(event) => {
                        event.stopPropagation()
                        setPreviewing(true)
                    }}
                >
                    <img src={profile.avatar_url} alt="" />
                </button>
                {previewing && (
                    <AvatarPreview src={profile.avatar_url} name={name} onClose={() => setPreviewing(false)} />
                )}
            </>
        )
    }

    return (
        <span className={classes.join(' ')} style={style} aria-hidden="true">
            {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : initials(profile)}
        </span>
    )
}
