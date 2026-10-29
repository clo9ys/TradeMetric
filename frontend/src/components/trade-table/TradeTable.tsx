import { TrashIcon } from '../icons/Icons';
import type { DemoInstrument, TradeRow, TradeRowError } from '../../types/session';
import './TradeTable.css';

interface Props {
  rows: TradeRow[];
  readOnly?: boolean;
  onChange?: (id: string, field: 'isin' | 'quantity', value: string) => void;
  onRemove?: (id: string) => void;
  instruments?: Record<string, DemoInstrument>;
  errors?: Record<string, TradeRowError>;
  onFieldBlur?: (id: string) => void;
}

export function TradeTable({ rows, readOnly = false, onChange, onRemove, instruments = {}, errors = {}, onFieldBlur }: Props) {
  return <div className="trade-table-scroll">
    <table className="trade-table">
      <caption className="sr-only">Сделки с облигациями</caption>
      <colgroup><col className="col-number" /><col className="col-isin" /><col className="col-name" /><col className="col-currency" /><col className="col-issuer" /><col className="col-quantity" /><col className="col-delete" /></colgroup>
      <thead><tr><th scope="col">#</th><th scope="col">ISIN</th><th scope="col">Наименование</th><th scope="col">Валюта</th><th scope="col">Эмитент</th><th scope="col">Объем</th><th scope="col"><span className="sr-only">Действия</span></th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={row.id}>
        <td className="row-number">{index + 1}</td>
        <td><input aria-label={`ISIN, строка ${index + 1}`} aria-invalid={Boolean(errors[row.id]?.isin)} aria-describedby={errors[row.id]?.isin ? `isin-error-${row.id}` : undefined} className="trade-input isin-input" placeholder="Введите ISIN" value={row.isin} maxLength={12} autoComplete="off" spellCheck={false} readOnly={readOnly} onBlur={() => onFieldBlur?.(row.id)} onChange={event => onChange?.(row.id, 'isin', event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} />{errors[row.id]?.isin && <small className="trade-field-error" id={`isin-error-${row.id}`}>{errors[row.id].isin}</small>}</td>
        <td><div className="empty-field">{instruments[row.isin]?.issue_name ?? '—'}</div></td>
        <td><div className="empty-field">{instruments[row.isin]?.currency ?? '—'}</div></td>
        <td><div className="empty-field" title={instruments[row.isin]?.issuer_name ?? undefined}>{instruments[row.isin]?.issuer_name || '—'}</div></td>
        <td><input aria-label={`Объём, строка ${index + 1}`} aria-invalid={Boolean(errors[row.id]?.quantity)} aria-describedby={errors[row.id]?.quantity ? `quantity-error-${row.id}` : undefined} className="trade-input" placeholder="0" value={row.quantity} type="text" inputMode="numeric" autoComplete="off" maxLength={15} readOnly={readOnly} onBlur={() => onFieldBlur?.(row.id)} onChange={event => onChange?.(row.id, 'quantity', event.target.value.replace(/[^0-9-]/g, '').replace(/(?!^)-/g, ''))} />{errors[row.id]?.quantity && <small className="trade-field-error" id={`quantity-error-${row.id}`}>{errors[row.id].quantity}</small>}</td>
        <td className="delete-cell"><button type="button" className="delete-button" aria-label={`Удалить строку ${index + 1}`} disabled={readOnly} onClick={() => onRemove?.(row.id)}><TrashIcon /></button></td>
      </tr>)}</tbody>
    </table>
  </div>;
}
