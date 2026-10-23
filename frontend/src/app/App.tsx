import { useEffect, useState } from 'react';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import { LoginPage } from '../pages/login/LoginPage';
import { NewSessionPage } from '../pages/new-session/NewSessionPage';
import { HistoryPage } from '../pages/history/HistoryPage';
import type { Currency, Page } from '../types/session';

function currentPage(): Page {
  if (location.hash === '#login') return 'login';
  if (location.hash === '#history') return 'history';
  return 'new';
}

export function App() {
  const [page, setPage] = useState<Page>(currentPage);
  const [currency, setCurrency] = useState<Currency>('RUB');

  useEffect(() => {
    const onHashChange = () => setPage(currentPage());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    const titles = { login: 'Вход', new: 'Новая сессия', history: 'История' };
    document.title = `TradeMetric — ${titles[page]}`;
  }, [page]);

  // Сохраняем черновик при переключении вкладок до перезагрузки страницы.
  return <>
    {page === 'login' && <LoginPage />}
    <div hidden={page === 'login'}>
      <WorkspaceLayout page={page} currency={currency} onCurrencyChange={setCurrency}>
        <div hidden={page !== 'new'}><NewSessionPage /></div>
        <div hidden={page !== 'history'}><HistoryPage /></div>
      </WorkspaceLayout>
    </div>
  </>;
}
