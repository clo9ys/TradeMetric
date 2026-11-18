import { ApiError, apiRequest, setCsrfToken } from './client';

export type UserRole = 'user' | 'admin';

export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
}

interface AuthResponse {
  user: CurrentUser;
  csrf_token: string;
}

export async function login(email: string, password: string): Promise<CurrentUser> {
  const data = await apiRequest<AuthResponse>('/api/auth/login', { method: 'POST', body: { email, password } });
  setCsrfToken(data.csrf_token);
  return data.user;
}

// null — сессии нет, нужно показать вход.
export async function fetchCurrentUser(signal?: AbortSignal): Promise<CurrentUser | null> {
  try {
    const data = await apiRequest<AuthResponse>('/api/auth/me', { signal });
    setCsrfToken(data.csrf_token);
    return data.user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<void>('/api/auth/logout', { method: 'POST' });
  } finally {
    setCsrfToken(null);
  }
}
