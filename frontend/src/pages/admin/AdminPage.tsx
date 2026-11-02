import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { CURRENT_USER_ID, readUsers, writeUsers } from './users';
import type { AdminUser, UserRole } from './users';
import './AdminPage.css';
import { Select } from '../../components/select/Select';

type Action = { kind: 'create' } | { kind: 'password' | 'delete' | 'role' | 'status'; user: AdminUser };

export function AdminPage() {
  const [initial] = useState(readUsers);
  const [users, setUsers] = useState(initial.users);
  const [storageError, setStorageError] = useState(initial.error);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [action, setAction] = useState<Action | null>(null);
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('user');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (action) dialog.current?.showModal();
    else dialog.current?.close();
  }, [action]);

  function open(next: Action) {
    setLogin(''); setPassword(''); setRole('user'); setError(''); setMessage(''); setAction(next);
  }
  function close() { setAction(null); setPassword(''); }
  function save(next: AdminUser[], notice: string) {
    setUsers(next);
    setStorageError(writeUsers(next) ? '' : 'Изменения действуют до перезагрузки: браузер не разрешил сохранить список.');
    setMessage(notice); close();
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action) return;
    if (action.kind === 'create' || action.kind === 'password') {
      if (password.length < 8 || password.length > 128 || !password.trim()) { setError('Введите пароль длиной от 8 до 128 символов.'); return; }
    }
    if (action.kind === 'create') {
      const name = login.trim();
      if (!/^[a-zA-Z0-9_.@+-]{3,64}$/.test(name)) { setError('Логин: от 3 до 64 латинских букв, цифр или символов _ . @ + -'); return; }
      if (users.some(user => user.login.toLowerCase() === name.toLowerCase())) { setError('Пользователь с таким логином уже существует.'); return; }
      save([...users, { id: crypto.randomUUID(), login: name, role, active: true, createdAt: new Date().toISOString() }], `Демо-пользователь «${name}» создан. Пароль не сохранён: сервер управления пользователями ещё не подключён.`);
    } else if (action.kind === 'password') {
      setMessage('Форма проверена. Пароль не изменён: для этого нужно подключить API управления пользователями.'); close();
    } else if (action.user.id !== CURRENT_USER_ID) {
      const user = action.user;
      if (action.kind === 'delete') save(users.filter(item => item.id !== user.id), `Демо-пользователь «${user.login}» удалён.`);
      else save(users.map(item => item.id !== user.id ? item : action.kind === 'role' ? { ...item, role: item.role === 'admin' ? 'user' : 'admin' } : { ...item, active: !item.active }), `Данные демо-пользователя «${user.login}» обновлены.`);
    }
  }
  const visible = users.filter(user => user.login.toLowerCase().includes(query.trim().toLowerCase()) && (roleFilter === 'all' || user.role === roleFilter));
  const title = action?.kind === 'create' ? 'Новый пользователь' : action?.kind === 'password' ? 'Изменить пароль' : action?.kind === 'delete' ? 'Удалить пользователя?' : action?.kind === 'role' ? 'Изменить роль?' : 'Изменить доступ?';

  return <section className="admin-page" aria-labelledby="admin-title">
    <div className="admin-heading"><div><p className="admin-eyebrow">Администрирование</p><h1 id="admin-title">Пользователи</h1><p>Управляйте пользователями и их доступом к системе</p></div><button className="button button-primary admin-add" onClick={() => open({ kind: 'create' })}><span aria-hidden="true">＋</span> Добавить пользователя</button></div>
    <p className="admin-demo">Демо-режим · Список хранится в этом браузере. Реальные аккаунты и пароли на сервере не изменяются.</p>
    <div className="admin-stats"><div><span>Всего пользователей</span><strong>{users.length}</strong></div><div><span>Администраторы</span><strong>{users.filter(user => user.role === 'admin').length}</strong></div><div><span>Активные</span><strong>{users.filter(user => user.active).length}</strong></div></div>
    {storageError && <p className="status-error" role="alert">{storageError}</p>}
    {message && <p className="admin-notice" role="status">{message}</p>}
    <div className="admin-panel">
      <div className="admin-toolbar"><label><span className="sr-only">Поиск по логину</span><input type="search" placeholder="Поиск по логину" value={query} onChange={event => setQuery(event.target.value)} /></label><Select label="Фильтр по роли" value={roleFilter} onChange={setRoleFilter} options={[{ value: 'all', label: 'Все роли' }, { value: 'admin', label: 'Администраторы' }, { value: 'user', label: 'Пользователи' }]} /></div>
      <div className="admin-table-scroll"><table className="admin-table"><caption className="sr-only">Пользователи системы</caption><thead><tr><th scope="col">Логин</th><th scope="col">Роль</th><th scope="col">Статус</th><th scope="col">Действия</th></tr></thead><tbody>{visible.map(user => <tr key={user.id}>
        <th scope="row"><div className="admin-identity"><span className="admin-avatar" aria-hidden="true">{user.login.slice(0, 2).toUpperCase()}</span><span>{user.login}{user.id === CURRENT_USER_ID && <small>Это вы · демо</small>}</span></div></th>
        <td><span className={`admin-role ${user.role}`}>{user.role === 'admin' ? 'admin' : 'user'}</span></td><td><span className={`admin-status ${user.active ? 'active' : ''}`}>{user.active ? 'Активен' : 'Заблокирован'}</span></td>
        <td><div className="admin-actions">{user.id !== CURRENT_USER_ID && <><button onClick={() => open({ kind: 'role', user })}>{user.role === 'admin' ? 'Снять admin' : 'Сделать admin'}</button><button onClick={() => open({ kind: 'status', user })}>{user.active ? 'Заблокировать' : 'Разблокировать'}</button></>}<button onClick={() => open({ kind: 'password', user })} aria-label={`Изменить пароль: ${user.login}`}>Пароль</button>{user.id !== CURRENT_USER_ID && <button className="admin-delete" aria-label={`Удалить пользователя ${user.login}`} onClick={() => open({ kind: 'delete', user })}>×</button>}</div></td>
      </tr>)}</tbody></table></div>
      {visible.length === 0 && <div className="admin-empty"><strong>Пользователи не найдены</strong><p>Попробуйте изменить поисковый запрос или роль.</p><button onClick={() => { setQuery(''); setRoleFilter('all'); }}>Сбросить фильтры</button></div>}
      <footer className="admin-table-footer">Показано {visible.length} из {users.length}<span>Доступ выдаётся администратором</span></footer>
    </div>
    <dialog className="admin-dialog" ref={dialog} aria-labelledby="admin-dialog-title" onCancel={close} onClose={() => { setAction(null); setPassword(''); }}>
      {action && <form onSubmit={submit}><div className="admin-dialog-heading"><h2 id="admin-dialog-title">{title}</h2><button type="button" className="admin-close" aria-label="Закрыть окно" onClick={close}>×</button></div>
        {action.kind !== 'create' && <p className="admin-dialog-login">{action.user.login}</p>}
        {action.kind === 'create' && <label className="admin-field">Логин *<input autoFocus required maxLength={64} value={login} onChange={event => { setLogin(event.target.value); setError(''); }} placeholder="Например, ivanov" autoComplete="off" /></label>}
        {(action.kind === 'create' || action.kind === 'password') && <><label className="admin-field">{action.kind === 'password' ? 'Новый пароль *' : 'Пароль *'}<input autoFocus={action.kind === 'password'} type="password" required minLength={8} maxLength={128} value={password} onChange={event => { setPassword(event.target.value); setError(''); }} autoComplete="new-password" aria-describedby="admin-password-hint" /></label><p id="admin-password-hint" className="admin-hint">От 8 до 128 символов. В демо пароль проверяется только в форме и не сохраняется.</p></>}
        {action.kind === 'create' && <div className="admin-field"><span>Роль</span><Select label="Роль" value={role} onChange={value => setRole(value as UserRole)} options={[{ value: 'user', label: 'user — пользователь' }, { value: 'admin', label: 'admin — администратор' }]} /></div>}
        {action.kind === 'delete' && <p>Пользователь будет удалён из демо-списка. Отменить удаление нельзя.</p>}
        {action.kind === 'role' && <p>Назначить роль <strong>{action.user.role === 'admin' ? 'user' : 'admin'}</strong> этому демо-пользователю?</p>}
        {action.kind === 'status' && <p>{action.user.active ? 'Заблокировать' : 'Восстановить'} доступ для этого демо-пользователя?</p>}
        {error && <p className="status-error" role="alert">{error}</p>}
        <div className="admin-dialog-footer"><button type="button" className="button button-secondary" autoFocus={action.kind === 'delete'} onClick={close}>Отмена</button><button type="submit" className={`button button-primary ${action.kind === 'delete' ? 'admin-danger' : ''}`}>{action.kind === 'create' ? 'Создать' : action.kind === 'delete' ? 'Удалить' : action.kind === 'password' ? 'Проверить форму' : 'Подтвердить'}</button></div>
      </form>}
    </dialog>
  </section>;
}
