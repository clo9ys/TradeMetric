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

export function ResultsCards({ result }: { result?: DemoCalculationResult | null }) {
  const values = result
    ? [money(result.total_dv01_rub, 6), money(result.total_fair_value_rub), String(result.trades.length)]
    : null;
  return <>
    <section className="results-cards" aria-label="Результаты расчёта">
      {metrics.map((metric, index) => <article className="metric-card" key={metric.name}>
        <h2>{metric.name}<span className="metric-info" tabIndex={0} aria-label={metric.description}><InfoIcon /><span className="metric-tooltip" role="tooltip">{metric.description}</span></span></h2>
        <p className={result ? 'metric-value' : 'metric-empty'}>{values?.[index] ?? <><span aria-hidden="true">—</span><span className="sr-only">Расчёт ещё не выполнен</span></>}</p>
      </article>)}
    </section>
    {result && <section className="trade-results" aria-label="Результат по сделкам">
      <h2>Результат по сделкам</h2>
      <div className="trade-results-scroll"><table><thead><tr><th>ISIN</th><th>Позиция</th><th>Стоимость, ₽</th><th>DV01, ₽</th></tr></thead><tbody>
        {result.trades.map((trade, index) => <tr key={`${trade.isin}-${index}`}><td>{trade.isin}</td><td>{trade.quantity}</td><td>{money(trade.fair_value_rub)}</td><td>{money(trade.dv01_rub, 6)}</td></tr>)}
      </tbody></table></div>
    </section>}
  </>;
}
