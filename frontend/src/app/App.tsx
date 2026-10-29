import { useEffect, useState } from 'react';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import { LoginPage } from '../pages/login/LoginPage';
import { NewSessionPage } from '../pages/new-session/NewSessionPage';
import { HistoryPage } from '../pages/history/HistoryPage';
import { DEFAULT_SESSION_NAME, normalizeSessionName, readSessionNames, writeSessionNames } from '../utils/sessionNames';
import type { Currency, DemoCalculationResult, Page } from '../types/session';

function currentPage(): Page {
  if (location.hash === '#login') return 'login';
  if (location.hash === '#history') return 'history';
  return 'new';
}

export function App() {
  const [page, setPage] = useState<Page>(currentPage);
  const [currency, setCurrency] = useState<Currency>('RUB');

  const [calculations, setCalculations] = useState<DemoCalculationResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [historyRevision, setHistoryRevision] = useState(0);
  const historyActive = page === 'history';
  const [sessionNames, setSessionNames] = useState(readSessionNames);
  const [nameStorageError, setNameStorageError] = useState('');
  const namedCalculations = calculations.map(item => ({ ...item, title: sessionNames[item.calculation_id] ?? item.title ?? DEFAULT_SESSION_NAME }));

  function saveSessionName(id: string, name: string) {
    const next = { ...sessionNames, [id]: normalizeSessionName(name) };
    setSessionNames(next);
    setNameStorageError(writeSessionNames(next) ? '' : 'Название изменено, но браузер не разрешил его сохранить. После перезагрузки оно сбросится.');
  }


  useEffect(() => {
    const controller = new AbortController();
    setHistoryLoading(true);
    setHistoryError('');
    fetch('/api/demo/history', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Не удалось загрузить историю. Попробуйте обновить страницу позже.');
        return response.json() as Promise<{ calculations: DemoCalculationResult[] }>;
      })
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
  }, [historyActive, historyRevision]);

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
      <WorkspaceLayout page={page} currency={currency} onCurrencyChange={setCurrency} calculations={namedCalculations} selectedHistoryId={selectedHistoryId} onHistorySelect={setSelectedHistoryId} historyLoading={historyLoading} historyError={historyError}>
        {nameStorageError && <p className="status-error" role="alert">{nameStorageError}</p>}
        <div hidden={page !== 'new'}><NewSessionPage onCalculated={(id, name) => { saveSessionName(id, name); setHistoryRevision(value => value + 1); }} /></div>
        <div hidden={page !== 'history'}><HistoryPage calculations={namedCalculations} selectedId={selectedHistoryId} onSelect={setSelectedHistoryId} loading={historyLoading} error={historyError} onRename={saveSessionName} onRetry={() => setHistoryRevision(value => value + 1)} /></div>
      </WorkspaceLayout>
    </div>
  </>;
}
