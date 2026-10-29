import { ChartIcon, DocumentIcon, UserIcon } from '../icons/Icons';
import type { Page } from '../../types/session';
import './Sidebar.css';

export function Sidebar({ page }: { page: Page }) {
  return <aside className="sidebar" aria-label="Боковая панель">
    <a className="brand" href="#new" aria-label="TradeMetric — новая сессия"><ChartIcon /><span>TradeMetric</span></a>
    <nav className="main-nav" aria-label="Разделы приложения">
      <a className={`nav-link ${page === 'new' ? 'selected' : ''}`} href="#new" aria-current={page === 'new' ? 'page' : undefined}><DocumentIcon /><span>Расчеты</span></a>
    </nav>
    <section className="recent" aria-labelledby="recent-heading">
      <h2 id="recent-heading">Недавние сессии</h2>
      <ul className="session-list" aria-label="Недавние сессии" />
    </section>
    <a className="profile" href="#login" aria-label="Пользователь — перейти к экрану входа"><span className="avatar"><UserIcon /></span><span>Пользователь</span></a>
  </aside>;
}
