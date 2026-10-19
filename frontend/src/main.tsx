import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/manrope/400.css';
import '@fontsource/manrope/500.css';
import '@fontsource/manrope/600.css';
import '@fontsource/manrope/700.css';
import './styles.css';

function ChartIcon() {
  return <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true"><path d="M2 14h8v13H2zM10 4h8v23h-8zM18 10h8v17h-8z" stroke="currentColor" strokeWidth="2.7" strokeLinejoin="round" /></svg>;
}

function DocumentIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /><path d="M13 3v6h6" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /></svg>;
}

function Sidebar() {
  return <aside className="sidebar" aria-label="Боковая панель">
    <a className="brand" href="#new" aria-label="TradeMetric — новая сессия"><ChartIcon /><span>TradeMetric</span></a>
    <nav className="main-nav" aria-label="Разделы приложения">
      <a className="nav-link" href="#new" aria-current="page"><DocumentIcon /><span>Расчеты</span></a>
    </nav>
    <section className="recent" aria-labelledby="recent-heading">
      <h2 id="recent-heading">Недавние сессии</h2>
      <ul className="session-list" aria-label="Недавние сессии" />
    </section>
    <div className="profile"><span className="avatar"><svg width="23" height="25" viewBox="0 0 24 26" fill="none" aria-hidden="true"><circle cx="12" cy="8" r="5" stroke="currentColor" strokeWidth="2" /><path d="M4 23v-1c0-4 3.6-6 8-6s8 2 8 6v1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></span><span>Пользователь</span></div>
  </aside>;
}

function App() {
  const [view, setView] = useState<'new' | 'history'>(() => location.hash === '#history' ? 'history' : 'new');
  const [currency, setCurrency] = useState('RUB');
  React.useEffect(() => {
    const updateView = () => setView(location.hash === '#history' ? 'history' : 'new');
    window.addEventListener('hashchange', updateView);
    return () => window.removeEventListener('hashchange', updateView);
  }, []);
  return <div className="app-shell">
    <Sidebar />
    <main className="workspace">
      <header className="workspace-header">
        <nav className="tabs" aria-label="Расчёты">
          <a className={`tab ${view === 'new' ? 'active' : ''}`} href="#new" aria-current={view === 'new' ? 'page' : undefined}>Новая сессия</a>
          <a className={`tab ${view === 'history' ? 'active' : ''}`} href="#history" aria-current={view === 'history' ? 'page' : undefined}>История</a>
        </nav>
        <label className="currency-picker"><span>Базовая валюта:</span><select aria-label="Базовая валюта" value={currency} onChange={event => setCurrency(event.target.value)}><option>RUB</option><option>USD</option><option>EUR</option></select><svg width="12" height="8" viewBox="0 0 12 8" fill="none" aria-hidden="true"><path d="m2 2 4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></label>
      </header>
      <section className="workspace-content" aria-label={view === 'new' ? 'Новая сессия' : 'История сессий'} />
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
