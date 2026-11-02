import { useEffect, useId, useRef, useState } from 'react';
import { ChevronIcon } from '../icons/Icons';
import './Select.css';

interface Props {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}

export function Select({ label, value, options, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();
  const selected = Math.max(0, options.findIndex(option => option.value === value));

  useEffect(() => {
    if (!open) return;
    const rect = trigger.current!.getBoundingClientRect();
    const dialog = root.current?.closest('dialog')?.getBoundingClientRect();
    const bottom = Math.min(window.innerHeight, dialog?.bottom ?? window.innerHeight);
    setAbove(bottom - rect.bottom < options.length * 48 + 24 && rect.top > options.length * 48 + 24);
    items.current[selected]?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open, selected, options.length]);

  return <div className="select-control" ref={root}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
    onKeyDown={event => {
      if (event.key === 'Escape' && open) {
        event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus();
      }
    }}>
    <button type="button" className="select-trigger" ref={trigger} aria-label={`${label}: ${options[selected]?.label}`}
      aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen(previous => !previous)}
      onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); } }}>
      <span>{options[selected]?.label}</span><ChevronIcon />
    </button>
    {open && <div className={`select-options${above ? ' select-options-above' : ''}`} role="listbox" aria-label={label} id={id}>
      {options.map((option, index) => <button type="button" key={option.value} role="option" aria-selected={option.value === value}
        className="select-option" ref={element => { items.current[index] = element; }}
        onMouseDown={event => { if (event.button === 0) event.preventDefault(); }}
        onKeyDown={event => {
          let next = index;
          if (event.key === 'ArrowDown') next = (index + 1) % options.length;
          else if (event.key === 'ArrowUp') next = (index + options.length - 1) % options.length;
          else if (event.key === 'Home') next = 0;
          else if (event.key === 'End') next = options.length - 1;
          else return;
          event.preventDefault(); items.current[next]?.focus();
        }}
        onClick={() => { onChange(option.value); setOpen(false); trigger.current?.focus(); }}>
        <span>{option.label}</span><span aria-hidden="true">{option.value === value ? '✓' : ''}</span>
      </button>)}
    </div>}
  </div>;
}
