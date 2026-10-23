import { useState } from 'react';
import { SessionPanel } from '../../components/session-panel/SessionPanel';
import { createEmptyTrades } from '../../types/session';

export function HistoryPage() {
  const [rows] = useState(createEmptyTrades);
  return <section aria-label="История сессий"><SessionPanel rows={rows} readOnly /><p className="sr-only">Сохранённых сессий пока нет.</p></section>;
}
