import { ChartIcon, DocumentIcon, UserIcon } from '../icons/Icons';
import type { DemoCalculationResult, Page } from '../../types/session';
import './Sidebar.css';

interface Props {
  page: Page;
  calculations: DemoCalculationResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string;
}

export function Sidebar({ page, calculations, selectedId, onSelect, loading, error }: Props) {
  return <aside className="sidebar" aria-label="Боковая панель">
    <a className="brand" href="#new" aria-label="TradeMetric — новая сессия"><ChartIcon /><span>TradeMetric</span></a>
    <nav className="main-nav" aria-label="Разделы приложения">
      <a className={`nav-link ${page === 'new' ? 'selected' : ''}`} href="#new" aria-current={page === 'new' ? 'page' : undefined}><DocumentIcon /><span>Расчеты</span></a>
    </nav>
    <section className="recent" aria-labelledby="recent-heading">
      <h2 id="recent-heading">Недавние сессии</h2>
      <ul className="session-list" aria-label="Недавние сессии" aria-busy={loading}>
        {calculations.map(item => <li key={item.calculation_id}>
          <a className={`recent-session ${page === 'history' && selectedId === item.calculation_id ? 'recent-session-selected' : ''}`}
            href="#history" onClick={() => onSelect(item.calculation_id)}
            aria-current={page === 'history' && selectedId === item.calculation_id ? 'true' : undefined}>
            <strong title={item.title}>{item.title || 'Новая сессия'}</strong>
            <time dateTime={item.calculated_at}>{item.calculated_at ? new Date(item.calculated_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : 'Сохранённый расчёт'}</time>
          </a>
        </li>)}
      </ul>
      {calculations.length === 0 && <p className="recent-status" role="status">{loading ? 'Загружаем сессии…' : error ? 'Не удалось загрузить сессии' : 'Сохранённых сессий пока нет'}</p>}
    </section>
    <a className="profile" href="#login" aria-label="Пользователь — перейти к экрану входа"><span className="avatar"><UserIcon /></span><span>Пользователь</span></a>
  </aside>;
}
