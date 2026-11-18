import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { changePassword, createUser, deleteUser, listUsers, updateUser } from '../../api/adminUsers';
import type { AdminUser } from '../../api/adminUsers';
import type { UserRole } from '../../api/auth';
import { ApiError } from '../../api/client';
import './AdminPage.css';
import { Select } from '../../components/select/Select';

type Action = { kind: 'create' } | { kind: 'password' | 'delete' | 'role' | 'status'; user: AdminUser };

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Props {
  currentUserId: string;
  // свой пароль сменили: сервер завершил все наши сессии, нужно войти заново
  onOwnPasswordChanged: () => void;
}

export function AdminPage({ currentUserId, onOwnPasswordChanged }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [action, setAction] = useState<Action | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('user');
  const [errors, setErrors] = useState({ login: '', password: '' });
  const [busy, setBusy] = useState(false);
  const loginInput = useRef<HTMLInputElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    listUsers(controller.signal)
      .then(list => { if (!controller.signal.aborted) { setUsers(list); setError(''); } })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Не удалось загрузить пользователей.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    if (action) dialog.current?.showModal();
    else dialog.current?.close();
  }, [action]);

  function open(next: Action) {
    setEmail(''); setPassword(''); setRole('user'); setErrors({ login: '', password: '' }); setMessage(''); setError(''); setAction(next);
  }
  function close() { setAction(null); setPassword(''); }
  function replace(updated: AdminUser) {
    setUsers(previous => previous.map(item => item.id === updated.id ? updated : item));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action || busy) return;
    if (action.kind === 'create' || action.kind === 'password') {
      const address = email.trim();
      const next = {
        login: action.kind !== 'create' ? '' : !address ? 'Введите email' : !EMAIL_PATTERN.test(address) ? 'Введите email в формате name@example.com' : users.some(user => user.email === address.toLowerCase()) ? 'Пользователь с таким email уже есть' : '',
        password: !password ? 'Введите пароль' : password.length < 8 || password.length > 128 || !password.trim() ? 'Пароль должен содержать от 8 до 128 символов' : '',
      };
      setErrors(next);
      if (next.login || next.password) {
        (next.login ? loginInput : passwordInput).current?.focus();
        return;
      }
    }

    setBusy(true);
    try {
      if (action.kind === 'create') {
        const created = await createUser(email.trim(), password, role);
        setUsers(previous => [...previous, created]);
        setMessage(`Пользователь «${created.email}» создан.`);
      } else if (action.kind === 'password') {
        await changePassword(action.user.id, password);
        if (action.user.id === currentUserId) { onOwnPasswordChanged(); return; }
        setMessage(`Пароль пользователя «${action.user.email}» изменён. Его сессии завершены.`);
      } else if (action.kind === 'delete') {
        await deleteUser(action.user.id);
        setUsers(previous => previous.filter(item => item.id !== action.user.id));
        setMessage(`Пользователь «${action.user.email}» удалён.`);
      } else if (action.kind === 'role') {
        replace(await updateUser(action.user.id, { role: action.user.role === 'admin' ? 'user' : 'admin' }));
        setMessage(`Роль пользователя «${action.user.email}» изменена.`);
      } else {
        replace(await updateUser(action.user.id, { is_active: !action.user.is_active }));
        setMessage(`Доступ пользователя «${action.user.email}» ${action.user.is_active ? 'заблокирован' : 'восстановлен'}.`);
      }
      close();
    } catch (reason) {
      const text = reason instanceof ApiError ? reason.message : 'Не удалось выполнить действие. Попробуйте ещё раз.';
      if (action.kind === 'create' && reason instanceof ApiError && reason.status === 409) {
        setErrors(previous => ({ ...previous, login: text }));
        loginInput.current?.focus();
        return;
      }
      setError(text);
      close();
    } finally {
      setBusy(false);
    }
  }
  const visible = users.filter(user => user.email.includes(query.trim().toLowerCase()) && (roleFilter === 'all' || user.role === roleFilter));
  const title = action?.kind === 'create' ? 'Новый пользователь' : action?.kind === 'password' ? 'Изменить пароль' : action?.kind === 'delete' ? 'Удалить пользователя?' : action?.kind === 'role' ? 'Изменить роль?' : 'Изменить доступ?';

  return <section className="admin-page" aria-labelledby="admin-title">
    <div className="admin-heading"><div><h1 id="admin-title">Пользователи</h1><p>Управляйте пользователями и их доступом к системе</p></div><button className="button button-primary admin-add" onClick={() => open({ kind: 'create' })}><span aria-hidden="true">＋</span> Добавить пользователя</button></div>
    <div className="admin-stats"><div><span>Всего пользователей</span><strong>{users.length}</strong></div><div><span>Администраторы</span><strong>{users.filter(user => user.role === 'admin').length}</strong></div><div><span>Активные</span><strong>{users.filter(user => user.is_active).length}</strong></div></div>
    {error && <p className="status-error" role="alert">{error} {!action && !loading && users.length === 0 && <button type="button" className="button button-secondary" onClick={() => setReload(value => value + 1)}>Повторить</button>}</p>}
    {message && <p className="admin-notice" role="status">{message}</p>}
    <div className="admin-panel" aria-busy={loading}>
      <div className="admin-toolbar"><label><span className="sr-only">Поиск по email</span><input type="search" placeholder="Поиск по email" value={query} onChange={event => setQuery(event.target.value)} /></label><Select label="Фильтр по роли" value={roleFilter} onChange={setRoleFilter} options={[{ value: 'all', label: 'Все роли' }, { value: 'admin', label: 'Администраторы' }, { value: 'user', label: 'Пользователи' }]} /></div>
      <div className="admin-table-scroll"><table className="admin-table"><caption className="sr-only">Пользователи системы</caption><thead><tr><th scope="col">Email</th><th scope="col">Роль</th><th scope="col">Статус</th><th scope="col">Действия</th></tr></thead><tbody>{visible.map(user => <tr key={user.id}>
        <th scope="row"><div className="admin-identity"><span className="admin-avatar" aria-hidden="true">{user.email.slice(0, 2).toUpperCase()}</span><span>{user.email}{user.id === currentUserId && <small>Это вы</small>}</span></div></th>
        <td><span className={`admin-role ${user.role}`}>{user.role === 'admin' ? 'admin' : 'user'}</span></td><td><span className={`admin-status ${user.is_active ? 'active' : ''}`}>{user.is_active ? 'Активен' : 'Заблокирован'}</span></td>
        <td><div className="admin-actions">{user.id !== currentUserId && <><button onClick={() => open({ kind: 'role', user })}>{user.role === 'admin' ? 'Снять admin' : 'Сделать admin'}</button><button onClick={() => open({ kind: 'status', user })}>{user.is_active ? 'Заблокировать' : 'Разблокировать'}</button></>}<button onClick={() => open({ kind: 'password', user })} aria-label={`Изменить пароль: ${user.email}`}>Пароль</button>{user.id !== currentUserId && <button className="admin-delete" aria-label={`Удалить пользователя ${user.email}`} onClick={() => open({ kind: 'delete', user })}>×</button>}</div></td>
      </tr>)}</tbody></table></div>
      {loading && users.length === 0 && <div className="admin-empty"><strong>Загружаем пользователей…</strong></div>}
      {!loading && visible.length === 0 && users.length > 0 && <div className="admin-empty"><strong>Пользователи не найдены</strong><p>Попробуйте изменить поисковый запрос или роль.</p><button onClick={() => { setQuery(''); setRoleFilter('all'); }}>Сбросить фильтры</button></div>}
      <footer className="admin-table-footer">Показано {visible.length} из {users.length}<span>Доступ выдаётся администратором</span></footer>
    </div>
    <dialog className="admin-dialog" ref={dialog} aria-labelledby="admin-dialog-title" onCancel={close} onClose={() => { setAction(null); setPassword(''); }}>
      {action && <form onSubmit={submit} noValidate><div className="admin-dialog-heading"><h2 id="admin-dialog-title">{title}</h2><button type="button" className="admin-close" aria-label="Закрыть окно" onClick={close}>×</button></div>
        {action.kind !== 'create' && <p className="admin-dialog-login">{action.user.email}</p>}
        {action.kind === 'create' && <label className="admin-field">Email *<input ref={loginInput} type="email" inputMode="email" aria-invalid={Boolean(errors.login)} aria-describedby="admin-login-error" autoFocus required maxLength={254} value={email} onChange={event => { setEmail(event.target.value); setErrors(previous => ({ ...previous, login: '' })); }} placeholder="Например, ivanov@bank.ru" autoComplete="off" /><span id="admin-login-error" className="admin-field-error" role="alert">{errors.login}</span></label>}
        {(action.kind === 'create' || action.kind === 'password') && <><label className="admin-field">{action.kind === 'password' ? 'Новый пароль *' : 'Пароль *'}<input ref={passwordInput} aria-invalid={Boolean(errors.password)} autoFocus={action.kind === 'password'} type="password" required minLength={8} maxLength={128} value={password} onChange={event => { setPassword(event.target.value); setErrors(previous => ({ ...previous, password: '' })); }} autoComplete="new-password" aria-describedby="admin-password-error admin-password-hint" /><span id="admin-password-error" className="admin-field-error" role="alert">{errors.password}</span></label><p id="admin-password-hint" className="admin-hint">От 8 до 128 символов.{action.kind === 'password' && action.user.id === currentUserId ? ' После смены пароля нужно будет войти заново.' : action.kind === 'password' ? ' Все сессии пользователя будут завершены.' : ''}</p></>}
        {action.kind === 'create' && <div className="admin-field"><span>Роль</span><Select label="Роль" value={role} onChange={value => setRole(value as UserRole)} options={[{ value: 'user', label: 'user — пользователь' }, { value: 'admin', label: 'admin — администратор' }]} /></div>}
        {action.kind === 'delete' && <p>Пользователь будет удалён, отменить это нельзя. Если у него есть история расчётов, удалить не получится: такого пользователя блокируют.</p>}
        {action.kind === 'role' && <p>Назначить роль <strong>{action.user.role === 'admin' ? 'user' : 'admin'}</strong> этому пользователю? Его сессии будут завершены.</p>}
        {action.kind === 'status' && <p>{action.user.is_active ? 'Заблокировать' : 'Восстановить'} доступ для этого пользователя?</p>}
        <div className="admin-dialog-footer"><button type="button" className="button button-secondary" autoFocus={action.kind === 'delete'} onClick={close}>Отмена</button><button type="submit" disabled={busy} className={`button button-primary ${action.kind === 'delete' ? 'admin-danger' : ''}`}>{busy ? 'Сохраняем…' : action.kind === 'create' ? 'Создать' : action.kind === 'delete' ? 'Удалить' : action.kind === 'password' ? 'Сохранить' : 'Подтвердить'}</button></div>
      </form>}
    </dialog>
  </section>;
}
