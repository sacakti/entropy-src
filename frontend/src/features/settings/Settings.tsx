import { useRef, useState, type FormEvent } from 'react'
import {
    Camera,
    KeyRound,
    LoaderCircle,
    Mail,
    RotateCcw,
    Save,
    ShieldCheck,
    Trash2,
    UserRound,
} from 'lucide-react'

import {
    removeAvatar,
    updateProfile,
    uploadAvatar,
    type Profile,
} from '../../api/profile.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import Avatar from './Avatar'
import ChangePasswordForm from './ChangePasswordForm'
import '../../styles/settings.css'
import EntropyLoader from '../../components/feedback/EntropyLoader'

const AVATAR_TYPES = 'image/jpeg,image/png,image/webp'

function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

export default function Settings({
    profile,
    onProfileChange,
}: {
    profile: Profile | null
    onProfileChange: (profile: Profile) => void
}) {
    const { notify, modal } = useFeedback()
    const fileRef = useRef<HTMLInputElement>(null)

    // Edits start from the loaded profile; `null` means "unchanged".
    const [fullName, setFullName] = useState<string | null>(null)
    const [email, setEmail] = useState<string | null>(null)
    const [saving, setSaving] = useState(false)
    const [avatarBusy, setAvatarBusy] = useState(false)
    const [passwordOpen, setPasswordOpen] = useState(false)

    if (!profile) {
        return (
            <EntropyLoader label="Loading your profile…" />
        )
    }

    const nameValue = fullName ?? profile.full_name ?? ''
    const emailValue = email ?? profile.email ?? ''
    const dirty =
        nameValue.trim() !== (profile.full_name ?? '') ||
        emailValue.trim() !== (profile.email ?? '')

    const reset = () => {
        setFullName(null)
        setEmail(null)
    }

    const save = async (event: FormEvent) => {
        event.preventDefault()

        if (!dirty || saving) return

        setSaving(true)

        try {
            const next = await updateProfile({
                full_name: nameValue.trim() || null,
                email: emailValue.trim() || null,
            })

            onProfileChange(next)
            reset()
            notify.success('Profile updated.')
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to update your profile.'))
        } finally {
            setSaving(false)
        }
    }

    const chooseAvatar = async (file: File | undefined) => {
        if (!file) return

        setAvatarBusy(true)

        try {
            onProfileChange(await uploadAvatar(file))
            notify.success('Profile picture updated.')
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to upload the picture.'))
        } finally {
            setAvatarBusy(false)
            if (fileRef.current) fileRef.current.value = ''
        }
    }

    const deleteAvatar = async () => {
        const confirmed = await modal.confirm({
            title: 'Remove profile picture?',
            message: 'Your initials will be shown instead.',
            confirmText: 'Remove',
            destructive: true,
        })

        if (!confirmed) return

        setAvatarBusy(true)

        try {
            onProfileChange(await removeAvatar())
            notify.success('Profile picture removed.')
        } catch (error) {
            notify.error(errorMessage(error, 'Unable to remove the picture.'))
        } finally {
            setAvatarBusy(false)
        }
    }

    return (
        <div className="list-page settings-page">
            <section className="dashboard-section list-section settings-card" aria-labelledby="settings-profile-title">
                <header className="settings-card-header">
                    <span className="settings-card-icon">
                        <UserRound size={18} />
                    </span>
                    <div>
                        <h2 id="settings-profile-title">Profile</h2>
                        <p>How you appear across Entropy.</p>
                    </div>
                </header>

                <div className="settings-avatar-row">
                    <Avatar profile={profile} size={84} zoomable />

                    <div className="settings-avatar-actions">
                        <strong>Profile picture</strong>
                        <span>JPEG, PNG or WebP up to 10 MB. Cropped to a square.</span>

                        <div>
                            <input
                                ref={fileRef}
                                type="file"
                                accept={AVATAR_TYPES}
                                hidden
                                onChange={(event) => void chooseAvatar(event.target.files?.[0])}
                            />
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => fileRef.current?.click()}
                                disabled={avatarBusy}
                            >
                                {avatarBusy ? (
                                    <LoaderCircle size={14} className="entropy-spin" />
                                ) : (
                                    <Camera size={14} />
                                )}
                                {profile.avatar_url ? 'Change picture' : 'Upload picture'}
                            </button>

                            {profile.avatar_url && (
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                                    onClick={() => void deleteAvatar()}
                                    disabled={avatarBusy}
                                >
                                    <Trash2 size={14} />
                                    Remove
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                <form className="settings-form" onSubmit={save}>
                    <label className="settings-field">
                        <span>Username</span>
                        <input value={profile.username} readOnly disabled />
                        <small>Usernames cannot be changed.</small>
                    </label>

                    <label className="settings-field">
                        <span>Full name</span>
                        <input
                            value={nameValue}
                            onChange={(event) => setFullName(event.target.value)}
                            placeholder="Your name"
                            maxLength={120}
                            autoComplete="name"
                        />
                    </label>

                    <label className="settings-field">
                        <span>Email</span>
                        <div className="settings-input-icon">
                            <Mail size={15} aria-hidden="true" />
                            <input
                                type="email"
                                value={emailValue}
                                onChange={(event) => setEmail(event.target.value)}
                                placeholder="name@example.com"
                                maxLength={254}
                                autoComplete="email"
                            />
                        </div>
                    </label>

                    <div className="settings-form-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            onClick={reset}
                            disabled={!dirty || saving}
                        >
                            <RotateCcw size={15} />
                            Reset
                        </button>
                        <button
                            type="submit"
                            className="entropy-button entropy-button-primary"
                            disabled={!dirty || saving}
                        >
                            {saving ? (
                                <LoaderCircle size={15} className="entropy-spin" />
                            ) : (
                                <Save size={15} />
                            )}
                            Save changes
                        </button>
                    </div>
                </form>
            </section>

            {!profile.auth_provider && <section className="dashboard-section list-section settings-card" aria-labelledby="settings-security-title">
                <header className="settings-card-header">
                    <span className="settings-card-icon">
                        <ShieldCheck size={18} />
                    </span>
                    <div>
                        <h2 id="settings-security-title">Security</h2>
                        <p>Keep your account protected.</p>
                    </div>
                </header>

                <div className="settings-row">
                    <div>
                        <strong>Password</strong>
                        <span>Confirm your current password before choosing a new one.</span>
                    </div>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => setPasswordOpen(true)}
                    >
                        <KeyRound size={15} />
                        Change password
                    </button>
                </div>
            </section>}

            {passwordOpen && (
                <Dialog
                    title="Change password"
                    subtitle="Use at least 8 characters. Common passwords are not allowed."
                    icon={<KeyRound size={18} />}
                    onClose={() => setPasswordOpen(false)}
                    className="settings-password-dialog"
                >
                    <ChangePasswordForm
                        onCancel={() => setPasswordOpen(false)}
                        onChanged={(message) => {
                            setPasswordOpen(false)
                            notify.success(message)
                        }}
                    />
                </Dialog>
            )}
        </div>
    )
}
