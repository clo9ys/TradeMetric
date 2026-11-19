import { useEffect, useState } from 'react';
import { fetchCurrentUser, logout } from '../api/auth';
import type { CurrentUser } from '../api/auth';
import { apiRequest, onUnauthorized } from '../api/client';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import { LoginPage } from '../pages/login/LoginPage';
import { NewSessionPage } from '../pages/new-session/NewSessionPage';
import { HistoryPage } from '../pages/history/HistoryPage';
import { AdminPage } from '../pages/admin/AdminPage';
import { DEFAULT_SESSION_NAME, normalizeSessionName, readSessionNames, writeSessionNames } from '../utils/sessionNames';
import type { Currency, CalculationResult, Page } from '../types/session';

function currentPage(): Page {
  if (location.hash === '#adm_new') return 'adm_new';
  if (location.hash === '#adm_history') return 'adm_history';
  if (location.hash === '#admin') return 'admin';
  if (location.hash === '#login') return 'login';
  if (location.hash === '#history') return 'history';
  return 'new';
}

export function App() {
  // undefined — ещё проверяем сессию, null — нужно войти
  const [user, setUser] = useState<CurrentUser | null | undefined>(undefined);
  const [page, setPage] = useState<Page>(currentPage);
  const [currency, setCurrency] = useState<Currency>('RUB');

  const [calculations, setCalculations] = useState<CalculationResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [historyRevision, setHistoryRevision] = useState(0);
  const isAdmin = user?.role === 'admin';
  const adminMode = isAdmin;
  // экран входа и чужой раздел «Управление» после входа ведут к расчётам
  const visiblePage: Page = page === 'login' || (page === 'admin' && !isAdmin) ? 'new' : page;
  const workspacePage = visiblePage === 'adm_new' ? 'new' : visiblePage === 'adm_history' ? 'history' : visiblePage;
  const historyActive = workspacePage === 'history';
  const [sessionNames, setSessionNames] = useState(readSessionNames);
  const [nameStorageError, setNameStorageError] = useState('');
  const namedCalculations = calculations.map(item => ({ ...item, title: sessionNames[item.calculation_id] ?? item.title ?? DEFAULT_SESSION_NAME }));

  function saveSessionName(id: string, name: string) {
    const next = { ...sessionNames, [id]: normalizeSessionName(name) };
    setSessionNames(next);
    setNameStorageError(writeSessionNames(next) ? '' : 'Название изменено, но браузер не разрешил его сохранить. После перезагрузки оно сбросится.');
  }


  useEffect(() => {
    onUnauthorized(() => setUser(null));
    const controller = new AbortController();
    fetchCurrentUser(controller.signal)
      .then(current => { if (!controller.signal.aborted) setUser(current); })
      .catch(() => { if (!controller.signal.aborted) setUser(null); });
    return () => { controller.abort(); onUnauthorized(null); };
  }, []);

  function handleLoggedIn(current: CurrentUser) {
    setUser(current);
    location.hash = current.role === 'admin' ? '#adm_new' : '#new';
  }

  async function handleLogout() {
    try { await logout(); } catch { /* сессия уже могла закончиться */ }
    setUser(null);
    location.hash = '#login';
  }

  const userId = user?.id;
  useEffect(() => {
    setCalculations([]);
    setSelectedHistoryId(null);
    if (!userId) return;
    const controller = new AbortController();
    setHistoryLoading(true);
    setHistoryError('');
    apiRequest<{ calculations: CalculationResult[] }>('/api/calculations', { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return;
        setCalculations(data.calculations);
        setSelectedHistoryId(previous => data.calculations.some(item => item.calculation_id === previous)
          ? previous : data.calculations[0]?.calculation_id ?? null);
        setHistoryError('');
      })
      .catch(reason => {
        if (!controller.signal.aborted) setHistoryError(reason instanceof Error ? reason.message : 'Не удалось загрузить историю.');
      })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => controller.abort();
  }, [historyActive, historyRevision, userId]);

  useEffect(() => {
    const onHashChange = () => {
      const next = currentPage();
      if (next === 'login') void handleLogout();
      setPage(next);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    const titles = { login: 'Вход', new: 'Новая сессия', history: 'История', admin: 'Пользователи', adm_new: 'Новая сессия', adm_history: 'История' };
    document.title = `TradeMetric — ${titles[user === null ? 'login' : visiblePage]}`;
  }, [user, visiblePage]);

  if (user === undefined) return <main className="app-loading" aria-busy="true" />;
  if (user === null) return <LoginPage onLoggedIn={handleLoggedIn} />;

  // Сохраняем черновик при переключении вкладок до перезагрузки страницы.
  return <>
    {visiblePage === 'admin' && <main className="admin-workspace"><header className="admin-workspace-header"><a className="admin-back" href="#adm_new">Вернуться к расчётам</a><span>Администрирование</span></header><AdminPage currentUserId={user.id} onOwnPasswordChanged={() => { setUser(null); location.hash = '#login'; }} /></main>}
    <div hidden={visiblePage === 'admin'}>
      <WorkspaceLayout adminMode={adminMode} page={workspacePage} currency={currency} onCurrencyChange={setCurrency} calculations={namedCalculations} selectedHistoryId={selectedHistoryId} onHistorySelect={setSelectedHistoryId} historyLoading={historyLoading} historyError={historyError}>
        {nameStorageError && <p className="status-error" role="alert">{nameStorageError}</p>}
        <div hidden={workspacePage !== 'new'}><NewSessionPage onCalculated={(id, name) => { saveSessionName(id, name); setHistoryRevision(value => value + 1); }} /></div>
        <div hidden={workspacePage !== 'history'}><HistoryPage calculations={namedCalculations} selectedId={selectedHistoryId} onSelect={setSelectedHistoryId} loading={historyLoading} error={historyError} onRename={saveSessionName} onRetry={() => setHistoryRevision(value => value + 1)} /></div>
      </WorkspaceLayout>
    </div>
  </>;
}
