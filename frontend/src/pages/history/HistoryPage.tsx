import { SessionNameEditor } from '../../components/session-name/SessionNameEditor';
import { DEFAULT_SESSION_NAME } from '../../utils/sessionNames';
import { SessionPanel } from '../../components/session-panel/SessionPanel';
import type { DemoCalculationResult, DemoInstrument, TradeRow } from '../../types/session';
import './HistoryPage.css';

interface Props {
  calculations: DemoCalculationResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string;
  onRename: (id: string, name: string) => void;
}

export function HistoryPage({ calculations, selectedId, onSelect, loading, error, onRename }: Props) {
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
        onClick={() => onSelect(item.calculation_id)}>
        <strong>{item.title || DEFAULT_SESSION_NAME}</strong><span>{item.calculated_at ? new Date(item.calculated_at).toLocaleString('ru-RU') : ''}</span>
        <span>{item.trades.length} сделок · DV01 {Number(item.total_dv01_rub).toLocaleString('ru-RU', { maximumFractionDigits: 6 })} ₽</span>
      </button>)}
    </div>}
    {selected && <div className="history-detail"><SessionNameEditor key={selected.calculation_id} name={selected.title || DEFAULT_SESSION_NAME} onSave={name => onRename(selected.calculation_id, name)} /><SessionPanel rows={rows} instruments={instruments} result={selected} readOnly /></div>}
  </section>;
}
