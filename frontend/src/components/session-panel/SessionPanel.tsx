import type { ReactNode } from 'react';
import { TradeTable } from '../trade-table/TradeTable';
import { ResultsCards } from '../results-cards/ResultsCards';
import { ArrowIcon, PlusIcon } from '../icons/Icons';
import type { TradeRow } from '../../types/session';
import './SessionPanel.css';

interface Props {
  rows: TradeRow[];
  readOnly?: boolean;
  onChange?: (id: string, field: 'isin' | 'quantity', value: string) => void;
  onRemove?: (id: string) => void;
  onAdd?: () => void;
  onCalculate?: () => void;
  message?: ReactNode;
}

export function SessionPanel({ rows, readOnly = false, onChange, onRemove, onAdd, onCalculate, message }: Props) {
  return <>
    <section className="session-panel" aria-label={readOnly ? 'Сохранённая сессия' : 'Ввод сделок'}>
      <TradeTable rows={rows} readOnly={readOnly} onChange={onChange} onRemove={onRemove} />
      <div className="session-actions">
        <button type="button" className="button button-secondary" disabled={readOnly} onClick={onAdd}><PlusIcon />Добавить</button>
        <button type="button" className="button button-primary calculate-button" disabled={readOnly} onClick={onCalculate}>Рассчитать<ArrowIcon /></button>
      </div>
    </section>
    {message && <p className="status-message" role="status">{message}</p>}
    <ResultsCards />
  </>;
}
