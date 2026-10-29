import type { ReactNode } from 'react';
import { TradeTable } from '../trade-table/TradeTable';
import { ResultsCards } from '../results-cards/ResultsCards';
import { ArrowIcon, PlusIcon } from '../icons/Icons';
import type { DemoCalculationResult, DemoInstrument, TradeRow, TradeRowError } from '../../types/session';
import './SessionPanel.css';

interface Props {
  rows: TradeRow[];
  readOnly?: boolean;
  onChange?: (id: string, field: 'isin' | 'quantity', value: string) => void;
  onRemove?: (id: string) => void;
  onAdd?: () => void;
  onCalculate?: () => void;
  onLoadDemo?: () => void;
  calculating?: boolean;
  instruments?: Record<string, DemoInstrument>;
  result?: DemoCalculationResult | null;
  message?: ReactNode;
  error?: boolean;
  rowErrors?: Record<string, TradeRowError>;
  onFieldBlur?: (id: string) => void;
}

export function SessionPanel({ rows, readOnly = false, onChange, onRemove, onAdd, onCalculate, onLoadDemo, calculating = false, instruments, result, message, error = false, rowErrors, onFieldBlur }: Props) {
  return <>
    {message && <p className={`status-message ${error ? 'status-error' : ''}`} role={error ? 'alert' : 'status'}>{message}</p>}
    <section className="session-panel" aria-label={readOnly ? 'Сохранённая сессия' : 'Ввод сделок'}>
      <TradeTable rows={rows} readOnly={readOnly} onChange={onChange} onRemove={onRemove} instruments={instruments} errors={rowErrors} onFieldBlur={onFieldBlur} />
      {!readOnly && <div className="session-actions">
        <div className="session-action-group">
          <button type="button" className="button button-secondary" disabled={readOnly || calculating} onClick={onAdd}><PlusIcon />Добавить</button>
          {onLoadDemo && <button type="button" className="button button-secondary" disabled={readOnly || calculating} onClick={onLoadDemo}>Загрузить демо</button>}
        </div>
        <button type="button" className="button button-primary calculate-button" disabled={readOnly || calculating} onClick={onCalculate}>{calculating ? 'Расчёт…' : 'Рассчитать'}<ArrowIcon /></button>
      </div>}
    </section>
    <ResultsCards result={result} />
  </>;
}
