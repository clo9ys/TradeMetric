import { useState } from 'react';
import { InfoIcon } from '../icons/Icons';
import type { DemoCalculationResult } from '../../types/session';
import './ResultsCards.css';

const metrics = [
  { name: 'DV01 (сумма)', description: 'Суммарная чувствительность стоимости к изменению ставки на один базисный пункт.' },
  { name: 'Стоимость', description: 'Стоимость сделок в базовой валюте.' },
  { name: 'Количество сделок', description: 'Количество сделок, включённых в расчёт.' },
];

function money(value: string, maximumFractionDigits = 2) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits }).format(Number(value)) + ' ₽';
}

type SortKey = 'quantity' | 'fair_value_rub' | 'dv01_rub';
const sortableColumns: { key: SortKey; label: string }[] = [
  { key: 'quantity', label: 'Количество позиций' },
  { key: 'fair_value_rub', label: 'Стоимость, ₽' },
  { key: 'dv01_rub', label: 'DV01, ₽' },
];

export function ResultsCards({ result }: { result?: DemoCalculationResult | null }) {
  const [sort, setSort] = useState<{ key: SortKey; ascending: boolean } | null>(null);
  const trades = (result?.trades ?? []).map((trade, index) => ({ trade, index }));
  if (sort) trades.sort((a, b) => {
    const difference = Number(a.trade[sort.key]) - Number(b.trade[sort.key]);
    return (sort.ascending ? difference : -difference) || a.index - b.index;
  });
  const values = result
    ? [money(result.total_dv01_rub, 6), money(result.total_fair_value_rub), String(result.trades.length)]
    : null;
  return <>
    <section className="results-cards" aria-label="Результаты расчёта">
      {metrics.map((metric, index) => <article className="metric-card" key={metric.name}>
        <h2>{metric.name}<span className="metric-info" tabIndex={0} aria-label={metric.description}><InfoIcon /><span className={`metric-tooltip${index === 2 ? ' metric-tooltip-single-line' : ''}`} role="tooltip">{metric.description}</span></span></h2>
        <p className={result ? 'metric-value' : 'metric-empty'}>{values?.[index] ?? <><span aria-hidden="true">—</span><span className="sr-only">Расчёт ещё не выполнен</span></>}</p>
      </article>)}
    </section>
    {result && <section className="trade-results" aria-label="Результат по сделкам">
      <h2>Результат по сделкам</h2>
      <div className="trade-results-scroll"><table><thead><tr><th scope="col">ISIN</th>{sortableColumns.map(column => <th key={column.key} scope="col" aria-sort={sort?.key === column.key ? (sort.ascending ? 'ascending' : 'descending') : 'none'}>
          <button type="button" className="results-sort" onClick={() => setSort(previous => previous?.key !== column.key ? { key: column.key, ascending: true } : previous.ascending ? { key: column.key, ascending: false } : null)}>
            {column.label}<span className="results-sort-arrow" aria-hidden="true">{sort?.key === column.key ? (sort.ascending ? '↑' : '↓') : '↕'}</span>
          </button>
        </th>)}</tr></thead><tbody>
        {trades.map(({ trade, index }) => <tr key={`${trade.isin}-${index}`}><td>{trade.isin}</td><td>{trade.quantity}</td><td>{money(trade.fair_value_rub)}</td><td>{money(trade.dv01_rub, 6)}</td></tr>)}
      </tbody></table></div>
    </section>}
  </>;
}
