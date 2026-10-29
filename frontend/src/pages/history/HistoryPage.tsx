import { useEffect, useState } from 'react';
import { SessionPanel } from '../../components/session-panel/SessionPanel';
import type { DemoCalculationResult, DemoInstrument, TradeRow } from '../../types/session';
import './HistoryPage.css';

export function HistoryPage({ active }: { active: boolean }) {
  const [calculations, setCalculations] = useState<DemoCalculationResult[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    fetch('/api/demo/history', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Не удалось загрузить историю. Проверьте работу backend.');
        return response.json() as Promise<{ calculations: DemoCalculationResult[] }>;
      })
      .then(data => {
        setCalculations(data.calculations);
        setSelectedId(previous => data.calculations.some(item => item.calculation_id === previous)
          ? previous : data.calculations[0]?.calculation_id ?? null);
        setError('');
      })
      .catch(reason => {
        if (reason instanceof Error && reason.name !== 'AbortError') setError(reason.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active]);

  const selected = calculations.find(item => item.calculation_id === selectedId);
  const rows: TradeRow[] = selected?.trades.map((trade, index) => ({
    id: `${selected.calculation_id}-${index}`, isin: trade.isin, quantity: String(trade.quantity),
  })) ?? [];
  const instruments: Record<string, DemoInstrument> = Object.fromEntries(selected?.trades.map(trade => [trade.isin, {
    isin: trade.isin, issue_name: trade.issue_name ?? '', issuer_name: trade.issuer_name ?? '', currency: trade.currency ?? 'RUB',
    coupon_type: trade.coupon_type ?? 'fixed', default_quantity: trade.quantity,
  }]) ?? []);

  return <section className="history-page" aria-label="История сессий">
    <h1>История расчётов</h1>
    {loading && <p role="status">Загружаем историю…</p>}
    {error && <p className="status-error" role="alert">{error}</p>}
    {!loading && !error && calculations.length === 0 && <p>Сохранённых расчётов пока нет. Выполните расчёт на вкладке «Новая сессия».</p>}
    {calculations.length > 0 && <div className="history-list" aria-label="Сохранённые расчёты">
      {calculations.map(item => <button type="button" key={item.calculation_id}
        className={`history-item ${item.calculation_id === selectedId ? 'history-item-selected' : ''}`}
        aria-pressed={item.calculation_id === selectedId}
        onClick={() => setSelectedId(item.calculation_id)}>
        <strong>{item.calculated_at ? new Date(item.calculated_at).toLocaleString('ru-RU') : 'Расчёт'}</strong>
        <span>{item.trades.length} сделок · DV01 {Number(item.total_dv01_rub).toLocaleString('ru-RU', { maximumFractionDigits: 6 })} ₽</span>
      </button>)}
    </div>}
    {selected && <div className="history-detail"><SessionPanel rows={rows} instruments={instruments} result={selected} readOnly /></div>}
  </section>;
}
