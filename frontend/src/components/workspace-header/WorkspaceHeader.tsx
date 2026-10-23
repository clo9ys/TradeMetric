import { ChevronIcon } from '../icons/Icons';
import type { Currency, Page } from '../../types/session';
import './WorkspaceHeader.css';

interface Props { page: Page; currency: Currency; onCurrencyChange: (currency: Currency) => void }
export function WorkspaceHeader({ page, currency, onCurrencyChange }: Props) {
  return <header className="workspace-header">
    <nav className="tabs" aria-label="Расчёты">
      <a className={`tab ${page === 'new' ? 'active' : ''}`} href="#new" aria-current={page === 'new' ? 'page' : undefined}>Новая сессия</a>
      <a className={`tab ${page === 'history' ? 'active' : ''}`} href="#history" aria-current={page === 'history' ? 'page' : undefined}>История</a>
    </nav>
    <label className="currency-picker"><span>Базовая валюта:</span><select aria-label="Базовая валюта" value={currency} onChange={event => onCurrencyChange(event.target.value as Currency)}><option>RUB</option><option>USD</option><option>EUR</option></select><ChevronIcon /></label>
  </header>;
}
