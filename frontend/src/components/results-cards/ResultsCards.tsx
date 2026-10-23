import { InfoIcon } from '../icons/Icons';
import './ResultsCards.css';

const metrics = [
  { name: 'DV01 (сумма)', description: 'Суммарная чувствительность стоимости к изменению ставки на один базисный пункт.' },
  { name: 'Стоимость', description: 'Стоимость сделок в базовой валюте.' },
  { name: 'Количество сделок', description: 'Количество сделок, включённых в расчёт.' },
];

export function ResultsCards() {
  return <section className="results-cards" aria-label="Результаты расчёта">
    {metrics.map(metric => <article className="metric-card" key={metric.name}>
      <h2>{metric.name}<span className="metric-info" tabIndex={0} aria-label={metric.description}><InfoIcon /><span className="metric-tooltip" role="tooltip">{metric.description}</span></span></h2>
      <p className="metric-empty"><span aria-hidden="true">—</span><span className="sr-only">Расчёт ещё не выполнен</span></p>
    </article>)}
  </section>;
}
