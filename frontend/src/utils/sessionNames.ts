const STORAGE_KEY = 'trademetric:session-names:v1';
export const SESSION_NAME_LIMIT = 80;
export const DEFAULT_SESSION_NAME = 'Новая сессия';
export type SessionNames = Record<string, string>;

export function normalizeSessionName(value: string): string {
  return value.trim().slice(0, SESSION_NAME_LIMIT) || DEFAULT_SESSION_NAME;
}

export function readSessionNames(): SessionNames {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === 'string').map(([id, name]) => [id, normalizeSessionName(name)]));
  } catch { return {}; }
}

export function writeSessionNames(names: SessionNames): boolean {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(names)); return true; }
  catch { return false; }
}
