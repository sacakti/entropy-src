import type { Profile } from '../../api/profile.api'

/** Initials for a display name, falling back to the username's first letter. */
function initials(profile: Pick<Profile, 'username' | 'full_name'>): string {
    const words = (profile.full_name ?? '').trim().split(/\s+/).filter(Boolean)

    if (words.length >= 2) return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase()
    if (words.length === 1) return words[0][0].toUpperCase()

    return profile.username.charAt(0).toUpperCase()
}

/** Profile picture, or initials on an accent tile when none is set. */
export default function Avatar({
    profile,
    size = 30,
    className,
}: {
    profile: Pick<Profile, 'username' | 'full_name' | 'avatar_url'>
    size?: number
    className?: string
}) {
    return (
        <span
            className={['entropy-avatar', className].filter(Boolean).join(' ')}
            style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
            aria-hidden="true"
        >
            {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : initials(profile)}
        </span>
    )
}
