import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { ChevronIcon } from '../icons/Icons';
import type { Currency, Page } from '../../types/session';
import './WorkspaceHeader.css';

interface Props { page: Page; currency: Currency; onCurrencyChange: (currency: Currency) => void }
const currencies: Currency[] = ['RUB', 'USD', 'EUR'];

export function WorkspaceHeader({ page, currency, onCurrencyChange }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const listId = useId();

  useEffect(() => {
    if (!isOpen) return;
    optionRefs.current[currencies.indexOf(currency)]?.focus();
    const handlePointerDown = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [isOpen, currency]);

  function handleOptionKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex = index;
    if (event.key === 'ArrowDown') nextIndex = (index + 1) % currencies.length;
    else if (event.key === 'ArrowUp') nextIndex = (index + currencies.length - 1) % currencies.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = currencies.length - 1;
    else return;
    event.preventDefault();
    optionRefs.current[nextIndex]?.focus();
  }

  return <header className="workspace-header">
    <nav className="tabs" aria-label="Расчёты">
      <a className={`tab ${page === 'new' ? 'active' : ''}`} href="#new" aria-current={page === 'new' ? 'page' : undefined}>Новая сессия</a>
      <a className={`tab ${page === 'history' ? 'active' : ''}`} href="#history" aria-current={page === 'history' ? 'page' : undefined}>История</a>
    </nav>
    <div className="currency-picker" ref={pickerRef}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false);
      }}
      onKeyDown={event => {
        if (event.key === 'Escape' && isOpen) {
          event.preventDefault();
          setIsOpen(false);
          triggerRef.current?.focus();
        }
      }}>
      <button type="button" className="currency-picker-trigger" ref={triggerRef}
        aria-haspopup="listbox" aria-expanded={isOpen} aria-controls={isOpen ? listId : undefined}
        onClick={() => setIsOpen(open => !open)}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setIsOpen(true);
          }
        }}>
        <span>Базовая валюта:</span><span>{currency}</span><ChevronIcon />
      </button>
      {isOpen && <div className="currency-picker-options" id={listId} role="listbox" aria-label="Базовая валюта">
        {currencies.map((option, index) => <button key={option} type="button"
          className="currency-picker-option" role="option" aria-selected={option === currency}
          ref={element => { optionRefs.current[index] = element; }}
          onKeyDown={event => handleOptionKeyDown(event, index)}
          // Safari может увести фокус в body до click и закрыть список через onBlur.
          // Сохраняем фокус до выбора, клавиатурная навигация остаётся прежней.
          onMouseDown={event => { if (event.button === 0) event.preventDefault(); }}
          onClick={() => {
            onCurrencyChange(option);
            setIsOpen(false);
            triggerRef.current?.focus();
          }}>
          <span>{option}</span><span aria-hidden="true">{option === currency ? '✓' : ''}</span>
        </button>)}
      </div>}
    </div>
  </header>;
}
