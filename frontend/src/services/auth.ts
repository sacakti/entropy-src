import { apiRequest } from "./api"

export interface AuthUser {
  id: number
  username: string
  full_name: string | null
  email: string | null
  avatar_url?: string | null
}

/** Lifetime and inactivity limit of the browser session. */
export interface SessionInfo {
  expires_at: string
  /** 0: no inactivity limit. */
  idle_timeout_seconds: number
  idle_expires_at: string | null
}

/** A previous sign-in: when, and from which address. */
export interface LastLogin {
  at: string
  address: string | null
}

interface CurrentUserResponse {
  user: AuthUser
  permissions: string[]
  expires_at: string
  session?: SessionInfo
  /** The sign-in before this one (null for a first sign-in). */
  last_login?: LastLogin | null
  /** Show the welcome tour (a new account that has not finished it). */
  tour?: boolean
}

interface CsrfResponse {
  csrf_token: string
}

async function getCsrfToken(): Promise<string> {
  const response = await fetch('/api/auth/csrf', {
    method: 'GET',
    credentials: 'same-origin',
  })

  if (!response.ok) {
    throw new Error(
      'Unable to authenticate. If the problem persists, please contact your administrator.',
    )
  }

  const data: CsrfResponse = await response.json()
  return data.csrf_token
}

export async function login(
  username: string,
  password: string,
): Promise<void> {
  const csrfToken = await getCsrfToken()

  const response = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail ?? 'Login failed. Check your credentials.')
  }
}

export async function getCurrentUser(): Promise<CurrentUserResponse> {
  const response = await fetch('/api/auth/me', {
    method: 'GET',
    credentials: 'same-origin',
  })

  if (!response.ok) {
    throw new Error('Not authenticated.')
  }

  return response.json()
}

export async function logout(): Promise<void> {
  const csrfToken = await getCsrfToken()

  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'X-CSRF-Token': csrfToken,
    },
  })

  if (!response.ok) {
    throw new Error('Logout failed.')
  }
}

interface ChangePasswordResponse {
    message: string
}

export async function changePassword(
    currentPassword: string,
    newPassword: string,
): Promise<ChangePasswordResponse> {
    return apiRequest<ChangePasswordResponse>(
        '/api/auth/change-password',
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
            }),
        },
    )
}
/** The welcome tour was finished or skipped. */
export async function finishTour(): Promise<void> {
  const csrfToken = await getCsrfToken()
  await fetch('/api/auth/tour', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': csrfToken },
  })
}

/** The user is active: restart the server's inactivity timer. */
export function keepSessionAlive(): Promise<SessionInfo> {
  return apiRequest<SessionInfo>('/api/auth/keepalive', { method: 'POST' })
}

/** When the session ends; asking does not count as activity. */
export function sessionStatus(): Promise<SessionInfo> {
  return apiRequest<SessionInfo>('/api/auth/session')
}
