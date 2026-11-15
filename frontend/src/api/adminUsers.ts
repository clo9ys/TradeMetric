import { apiRequest } from './client';
import type { UserRole } from './auth';

export interface AdminUser {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

const BASE = '/api/admin/users';

export function listUsers(signal?: AbortSignal) {
  return apiRequest<AdminUser[]>(BASE, { signal });
}

export function createUser(email: string, password: string, role: UserRole) {
  return apiRequest<AdminUser>(BASE, { method: 'POST', body: { email, password, role } });
}

export function updateUser(id: string, changes: { role?: UserRole; is_active?: boolean }) {
  return apiRequest<AdminUser>(`${BASE}/${id}`, { method: 'PATCH', body: changes });
}

export function changePassword(id: string, password: string) {
  return apiRequest<void>(`${BASE}/${id}/password`, { method: 'PUT', body: { password } });
}

export function deleteUser(id: string) {
  return apiRequest<void>(`${BASE}/${id}`, { method: 'DELETE' });
}
