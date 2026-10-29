import type { ReactNode } from 'react';
import { Sidebar } from '../components/sidebar/Sidebar';
import { WorkspaceHeader } from '../components/workspace-header/WorkspaceHeader';
import type { Currency, DemoCalculationResult, Page } from '../types/session';
import './WorkspaceLayout.css';

interface Props { children: ReactNode; page: Page; currency: Currency; onCurrencyChange: (currency: Currency) => void;
  calculations: DemoCalculationResult[]; selectedHistoryId: string | null;
  onHistorySelect: (id: string) => void; historyLoading: boolean; historyError: string;
}
export function WorkspaceLayout({ children, calculations, selectedHistoryId, onHistorySelect, historyLoading, historyError, ...headerProps }: Props) {
  return <div className="app-shell"><Sidebar page={headerProps.page} calculations={calculations} selectedId={selectedHistoryId} onSelect={onHistorySelect} loading={historyLoading} error={historyError} /><main className="workspace"><WorkspaceHeader {...headerProps} /><div className="workspace-content">{children}</div></main></div>;
}
