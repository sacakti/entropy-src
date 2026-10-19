import { ArrowLeft, LockKeyhole } from 'lucide-react'

/** Shown in place of a page the signed-in user may not open. */
export default function AccessRestricted({
    page,
    permissions,
    onBack,
}: {
    page: string
    permissions: string[]
    onBack?: () => void
}) {
    return (
        <section className="access-restricted" role="alert">
            <span className="access-restricted-icon" aria-hidden="true">
                <LockKeyhole size={28} />
            </span>
            <h2>Access Restricted</h2>
            <p>
                You don&apos;t have permission to open <strong>{page}</strong>. Ask an administrator for{' '}
                {permissions.length > 1 ? 'one of these permissions' : 'this permission'}:
            </p>
            <div className="access-restricted-permissions">
                {permissions.map((permission) => (
                    <code key={permission}>{permission}</code>
                ))}
            </div>
            {onBack && (
                <button type="button" className="entropy-button entropy-button-secondary" onClick={onBack}>
                    <ArrowLeft size={15} />
                    Go back
                </button>
            )}
        </section>
    )
}
