// Общий клиент API: JSON, CSRF-токен на изменяющих запросах, единая обработка 401.

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

let csrfToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

// Вызывается, когда сессия кончилась: истекла, пароль сменили, аккаунт заблокировали.
export function onUnauthorized(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, { method = 'GET', body, signal }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, 'Сервер недоступен. Проверьте подключение и попробуйте ещё раз.');
  }

  // 401 на входе означает неверный пароль, а не потерянную сессию.
  if (response.status === 401 && path !== '/api/auth/login') unauthorizedHandler?.();
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function readError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === 'object' && 'detail' in data) {
      const { detail } = data as { detail: unknown };
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) return 'Проверьте заполнение полей.';
    }
  } catch {
    // ответ не JSON, ниже общий текст
  }
  return response.status >= 500 ? 'Ошибка на сервере. Попробуйте позже.' : 'Не удалось выполнить запрос.';
}
