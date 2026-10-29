import type { ReactNode } from 'react';
import { Sidebar } from '../components/sidebar/Sidebar';
import { WorkspaceHeader } from '../components/workspace-header/WorkspaceHeader';
import type { Currency, Page } from '../types/session';
import './WorkspaceLayout.css';

interface Props { children: ReactNode; page: Page; currency: Currency; onCurrencyChange: (currency: Currency) => void }
export function WorkspaceLayout({ children, ...headerProps }: Props) {
  return <div className="app-shell"><Sidebar page={headerProps.page} /><main className="workspace"><WorkspaceHeader {...headerProps} /><div className="workspace-content">{children}</div></main></div>;
}
