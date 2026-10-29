import { RequestState } from '../../components/request-state/RequestState';
import { useEffect, useState } from 'react';
import { DEFAULT_SESSION_NAME, SESSION_NAME_LIMIT } from '../../utils/sessionNames';
import '../../components/session-name/SessionNameEditor.css';
import { SessionPanel } from '../../components/session-panel/SessionPanel';
import { createEmptyTrade, createEmptyTrades } from '../../types/session';
import type { DemoCalculationResult, DemoInstrument, TradeRow, TradeRowError } from '../../types/session';

function validateRow(row: TradeRow, instruments: Record<string, DemoInstrument>): TradeRowError {
  if (!row.isin && !row.quantity) return {};
  const error: TradeRowError = {};
  if (!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(row.isin)) {
    error.isin = 'ISIN должен содержать 12 символов: две буквы, девять знаков и контрольную цифру.';
  } else if (Object.keys(instruments).length > 0 && !instruments[row.isin]) {
    error.isin = 'Этот ISIN отсутствует в списке доступных инструментов.';
  }
  if (!/^-?\d+$/.test(row.quantity) || Number(row.quantity) === 0 || !Number.isSafeInteger(Number(row.quantity))) {
    error.quantity = 'Укажите ненулевое целое количество бумаг.';
  }
  return error;
}

export function NewSessionPage({ onCalculated }: { onCalculated: (id: string, name: string) => void }) {
  const [name, setName] = useState('');
  const [rows, setRows] = useState<TradeRow[]>(createEmptyTrades);
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<DemoCalculationResult | null>(null);
  const [instruments, setInstruments] = useState<Record<string, DemoInstrument>>({});
  const [instrumentsLoading, setInstrumentsLoading] = useState(true);
  const [instrumentsError, setInstrumentsError] = useState('');
  const [instrumentsRevision, setInstrumentsRevision] = useState(0);
  const [calculationError, setCalculationError] = useState('');
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState(false);
  const [touchedRows, setTouchedRows] = useState<Set<string>>(new Set());
  const [validationRequested, setValidationRequested] = useState(false);
  const rowErrors = Object.fromEntries(rows.filter(row => validationRequested || touchedRows.has(row.id)).map(row => [row.id, validateRow(row, instruments)]));

  useEffect(() => {
    const controller = new AbortController();
    setInstrumentsLoading(true);
    setInstrumentsError('');
    fetch('/api/demo/instruments', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Не удалось загрузить инструменты. Попробуйте обновить страницу позже.');
        return response.json() as Promise<{ instruments: DemoInstrument[] }>;
      })
      .then(data => {
        if (controller.signal.aborted) return;
        setInstruments(Object.fromEntries(data.instruments.map(item => [item.isin, item])));
      })
      .catch(() => {
        if (!controller.signal.aborted) setInstrumentsError('Не удалось загрузить доступные инструменты.');
      })
      .finally(() => { if (!controller.signal.aborted) setInstrumentsLoading(false); });
    return () => controller.abort();
  }, [instrumentsRevision]);

  function updateRow(id: string, field: 'isin' | 'quantity', value: string) {
    setRows(previous => previous.map(row => row.id === id ? { ...row, [field]: value } : row));
    setResult(null);
    setCalculationError('');
    setMessage('');
    setError(false);
  }

  function loadDemo() {
    setCalculationError('');
    setRows(Object.values(instruments).map(instrument => ({
      id: crypto.randomUUID(), isin: instrument.isin, quantity: String(instrument.default_quantity),
    })));
    setResult(null);
    setTouchedRows(new Set());
    setValidationRequested(false);
    setError(false);
    setMessage('');
  }

  async function calculate() {
    if (calculating || instrumentsLoading || instrumentsError || !Object.keys(instruments).length) return;
    setCalculationError('');
    setValidationRequested(true);
    const enteredRows = rows.filter(row => row.isin || row.quantity);
    if (enteredRows.length === 0) {
      setMessage('Введите ISIN и объём хотя бы одной сделки.');
      setError(true);
      return;
    }
    if (enteredRows.some(row => Object.keys(validateRow(row, instruments)).length > 0)) {
      setMessage('Исправьте выделенные поля в таблице.');
      setError(true);
      return;
    }
    setCalculating(true);
    setError(false);
    setMessage('');
    try {
      const response = await fetch('/api/demo/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trades: enteredRows.map(row => ({ isin: row.isin, quantity: Number(row.quantity) })) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка расчёта');
      setResult(data as DemoCalculationResult);
      onCalculated((data as DemoCalculationResult).calculation_id, name);
      setError(false);
      setMessage('');
    } catch (error) {
      setResult(null);
      setCalculationError(error instanceof TypeError || error instanceof SyntaxError ? 'Сервис временно недоступен. Проверьте соединение и попробуйте ещё раз.' : error instanceof Error ? error.message : 'Не удалось выполнить расчёт.');
    } finally {
      setCalculating(false);
    }
  }

  return <section aria-label="Новая сессия">
    <div className="session-name-form"><label htmlFor="new-session-name">Название сессии</label><div className="session-name-controls"><input id="new-session-name" value={name} disabled={calculating} maxLength={SESSION_NAME_LIMIT} placeholder={DEFAULT_SESSION_NAME} onChange={event => setName(event.target.value)} /></div><span className="session-name-hint">Например, «Портфель ОФЗ». Название сохраняется в этом браузере.</span></div>
    {instrumentsLoading && <RequestState kind="loading" compact title="Загружаем инструменты…">Введённые сделки останутся в таблице.</RequestState>}
    {!instrumentsLoading && instrumentsError && <RequestState kind="error" compact title="Инструменты недоступны" onRetry={() => setInstrumentsRevision(value => value + 1)}>Проверьте соединение и повторите загрузку. Введённые сделки остаются в таблице.</RequestState>}
    {!instrumentsLoading && !instrumentsError && !Object.keys(instruments).length && <RequestState kind="empty" compact title="Нет доступных инструментов" onRetry={() => setInstrumentsRevision(value => value + 1)}>Попробуйте обновить список позже.</RequestState>}
    {calculationError && <RequestState kind="error" compact title="Не удалось выполнить расчёт" onRetry={() => void calculate()}>{calculationError}</RequestState>}
    {calculating && <RequestState kind="loading" compact title="Выполняем расчёт…">Получаем результаты по вашим сделкам.</RequestState>}
    <SessionPanel
      rows={rows} onChange={updateRow}
      onAdd={() => { setRows(previous => [...previous, createEmptyTrade()]); setResult(null); setCalculationError(''); setMessage(''); setError(false); }}
      onRemove={id => { setRows(previous => previous.filter(row => row.id !== id)); setResult(null); setCalculationError(''); setMessage(''); setError(false); }}
      onLoadDemo={Object.keys(instruments).length ? loadDemo : undefined}
      onCalculate={calculate} calculating={calculating} calculateDisabled={instrumentsLoading || Boolean(instrumentsError) || !Object.keys(instruments).length} message={message} error={error}
      rowErrors={rowErrors} onFieldBlur={id => setTouchedRows(previous => new Set(previous).add(id))}
      instruments={instruments} result={result}
    />
  </section>;
}
