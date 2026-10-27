
import { useState, type FormEvent } from 'react'
import {
    Eye,
    EyeOff,
    KeyRound,
    LoaderCircle,
} from 'lucide-react'

import { changePassword } from '../../services/auth'
import '../../styles/settings.css'
import { useErrorToast } from '../../components/feedback/useToast'

type PasswordFields = {
    currentPassword: string
    newPassword: string
    confirmPassword: string
}

const initialFields: PasswordFields = {
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
}

type Visibility = {
    current: boolean
    next: boolean
    confirm: boolean
}

export default function ChangePasswordForm({
    onCancel,
    onChanged,
}: {
    onCancel: () => void
    onChanged: (message: string) => void
}) {
    const [fields, setFields] =
        useState<PasswordFields>(initialFields)

    const [visibility, setVisibility] = useState<Visibility>({
        current: false,
        next: false,
        confirm: false,
    })

    const [error, setError] = useState('')
    useErrorToast(error)
    const [loading, setLoading] = useState(false)

    function updateField(
        field: keyof PasswordFields,
        value: string,
    ) {
        setFields((previous) => ({
            ...previous,
            [field]: value,
        }))
        setError('')
    }

    function toggleVisibility(field: keyof Visibility) {
        setVisibility((previous) => ({
            ...previous,
            [field]: !previous[field],
        }))
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()

        if (loading) return

        setError('')

        if (!fields.currentPassword) {
            setError('Enter your current password.')
            return
        }

        if (fields.newPassword.length < 8) {
            setError('Your new password must contain at least 8 characters.')
            return
        }

        if (fields.newPassword.trim().length === 0) {
            setError('Your new password cannot contain only whitespace.')
            return
        }

        if (
            ['password', 'password123', 'admin123'].includes(
                fields.newPassword.toLowerCase(),
            )
        ) {
            setError('Choose a less common password.')
            return
        }

        if (fields.newPassword !== fields.confirmPassword) {
            setError('The new passwords do not match.')
            return
        }

        setLoading(true)

        try {
            const response = await changePassword(
                fields.currentPassword,
                fields.newPassword,
            )

            setFields(initialFields)
            setVisibility({
                current: false,
                next: false,
                confirm: false,
            })

            onChanged(response.message || 'Password changed successfully.')
        } catch (err: unknown) {
            setError(
                err instanceof Error
                    ? err.message
                    : 'Unable to change your password. Please try again.',
            )
        } finally {
            setLoading(false)
        }
    }

    function renderPasswordField(
        field: keyof PasswordFields,
        label: string,
        placeholder: string,
        visibleKey: keyof Visibility,
        autoComplete: string,
    ) {
        const inputId = `entropy-${field}`

        return (
            <div className="password-field" key={field}>
                <label htmlFor={inputId}>{label}</label>

                <div className="password-input-wrap">
                    <input
                        id={inputId}
                        type={visibility[visibleKey] ? 'text' : 'password'}
                        value={fields[field]}
                        onChange={(event) =>
                            updateField(field, event.target.value)
                        }
                        placeholder={placeholder}
                        autoComplete={autoComplete}
                        required
                        disabled={loading}
                        minLength={field === 'currentPassword' ? undefined : 8}
                    />

                    <button
                        type="button"
                        className="password-visibility"
                        onClick={() => toggleVisibility(visibleKey)}
                        aria-label={
                            visibility[visibleKey]
                                ? `Hide ${label.toLowerCase()}`
                                : `Show ${label.toLowerCase()}`
                        }
                        aria-pressed={visibility[visibleKey]}
                        disabled={loading}
                    >
                        {visibility[visibleKey]
                            ? <EyeOff size={17} />
                            : <Eye size={17} />}
                    </button>
                </div>
            </div>
        )
    }

    return (
        <>
            <form
                className="password-change-form"
                onSubmit={handleSubmit}
                noValidate
            >
                {renderPasswordField(
                    'currentPassword',
                    'Current password',
                    'Enter current password',
                    'current',
                    'current-password',
                )}

                {renderPasswordField(
                    'newPassword',
                    'New password',
                    'Enter new password',
                    'next',
                    'new-password',
                )}

                {renderPasswordField(
                    'confirmPassword',
                    'Confirm new password',
                    'Enter new password again',
                    'confirm',
                    'new-password',
                )}

                <p className="password-hint">
                    Use at least 8 characters. Common passwords are not allowed.
                </p>



                <div className="password-form-actions">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        disabled={loading}
                        onClick={onCancel}
                    >
                        Cancel
                    </button>

                    <button
                        type="submit"
                        className="entropy-button entropy-button-primary"
                        disabled={loading}
                    >
                        {loading ? (
                            <>
                                <LoaderCircle
                                    size={16}
                                    className="password-spinner"
                                />
                                Updating...
                            </>
                        ) : (
                            <>
                                <KeyRound size={16} />
                                Update password
                            </>
                        )}
                    </button>
                </div>
            </form>
        </>
    )
}