import type { ReactNode } from 'react';
import './RequestState.css';

interface Props {
  kind: 'loading' | 'error' | 'empty';
  title: string;
  children?: ReactNode;
  compact?: boolean;
  onRetry?: () => void;
  action?: ReactNode;
}

export function RequestState({ kind, title, children, compact = false, onRetry, action }: Props) {
  return <div className={`request-state request-state-${kind}${compact ? ' request-state-compact' : ''}`} role={kind === 'error' ? 'alert' : 'status'} aria-live={kind === 'error' ? 'assertive' : 'polite'}>
    {kind === 'loading' && <span className="request-spinner" aria-hidden="true" />}
    <div className="request-state-copy"><h2>{title}</h2>{children && <p>{children}</p>}</div>
    {onRetry && <button type="button" className="request-state-action" onClick={onRetry}>Повторить</button>}
    {action}
  </div>;
}
