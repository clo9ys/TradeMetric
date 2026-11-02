import { useState } from 'react';
import { SESSION_NAME_LIMIT } from '../../utils/sessionNames';
import './SessionNameEditor.css';

interface Props { name: string; onSave: (name: string) => void }
export function SessionNameEditor({ name, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  if (!editing) return <div className="session-name-heading"><h2>{name}</h2><button type="button" className="rename-session" onClick={() => { setDraft(name); setEditing(true); }}>Переименовать</button></div>;
  return <form className="session-name-form" onSubmit={event => { event.preventDefault(); onSave(draft); setEditing(false); }} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); setEditing(false); } }}>
    <label htmlFor="saved-session-name">Название сессии</label>
    <div className="session-name-controls"><input id="saved-session-name" autoFocus value={draft} maxLength={SESSION_NAME_LIMIT} onChange={event => setDraft(event.target.value)} /><button type="submit" className="rename-session">Сохранить</button><button type="button" className="rename-session" onClick={() => setEditing(false)}>Отмена</button></div>
    <span className="session-name-hint">Enter — сохранить, Esc — отменить</span>
  </form>;
}
