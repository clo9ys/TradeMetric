export type UserRole = 'user' | 'admin';
export interface AdminUser { id: string; login: string; role: UserRole; active: boolean; createdAt: string }
const KEY = 'trademetric.admin.demo-users.v1';
export const CURRENT_USER_ID = 'demo-admin';
const initialUsers: AdminUser[] = [
  { id: CURRENT_USER_ID, login: 'admin_developer', role: 'admin', active: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'demo-admin-2', login: 'admin_ceo', role: 'admin', active: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'demo-user', login: 'engineer1', role: 'user', active: true, createdAt: '2026-01-01T00:00:00Z' },
];
export function readUsers(): { users: AdminUser[]; error: string } {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw === null) return { users: initialUsers, error: '' };
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data) || !data.every(item => item && typeof item.id === 'string' && typeof item.login === 'string' && ['user', 'admin'].includes(item.role) && typeof item.active === 'boolean' && typeof item.createdAt === 'string') || !data.some(item => item.id === CURRENT_USER_ID && item.active && item.role === 'admin') || new Set(data.map(item => item.id)).size !== data.length) throw new Error();
    return { users: data as AdminUser[], error: '' };
  } catch { return { users: initialUsers, error: 'Не удалось прочитать сохранённый список. Показаны исходные демо-пользователи.' }; }
}
export function writeUsers(users: AdminUser[]): boolean {
  try { localStorage.setItem(KEY, JSON.stringify(users)); return true; } catch { return false; }
}
