export interface AuthUser {
  id: number
  username: string
  full_name: string
  email: string | null
}

interface CurrentUserResponse {
  user: AuthUser
  permissions: string[]
  expires_at: string
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
    throw new Error('Unable to initialize secure login.')
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
