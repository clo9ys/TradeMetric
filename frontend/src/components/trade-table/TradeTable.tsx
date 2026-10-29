import { TrashIcon } from '../icons/Icons';
import type { TradeRow } from '../../types/session';
import './TradeTable.css';

interface Props {
  rows: TradeRow[];
  readOnly?: boolean;
  onChange?: (id: string, field: 'isin' | 'quantity', value: string) => void;
  onRemove?: (id: string) => void;
}

export function TradeTable({ rows, readOnly = false, onChange, onRemove }: Props) {
  return <div className="trade-table-scroll">
    <table className="trade-table">
      <caption className="sr-only">Сделки с облигациями</caption>
      <colgroup><col className="col-number" /><col className="col-isin" /><col className="col-name" /><col className="col-currency" /><col className="col-type" /><col className="col-quantity" /><col className="col-delete" /></colgroup>
      <thead><tr><th scope="col">#</th><th scope="col">ISIN</th><th scope="col">Наименование</th><th scope="col">Валюта</th><th scope="col">Тип</th><th scope="col">Объем</th><th scope="col"><span className="sr-only">Действия</span></th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={row.id}>
        <td className="row-number">{index + 1}</td>
        <td><input aria-label={`ISIN, строка ${index + 1}`} className="trade-input isin-input" placeholder="Введите ISIN" value={row.isin} maxLength={12} autoComplete="off" spellCheck={false} readOnly={readOnly} onChange={event => onChange?.(row.id, 'isin', event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} /></td>
        <td><div className="empty-field" aria-label="Наименование не загружено">—</div></td>
        <td><div className="empty-field" aria-label="Валюта не загружена">—</div></td>
        <td><div className="empty-field" aria-label="Тип не загружен">—</div></td>
        <td><input aria-label={`Объём, строка ${index + 1}`} className="trade-input" placeholder="0" value={row.quantity} type="text" inputMode="numeric" autoComplete="off" maxLength={15} readOnly={readOnly} onChange={event => onChange?.(row.id, 'quantity', event.target.value.replace(/[^0-9]/g, ''))} /></td>
        <td className="delete-cell"><button type="button" className="delete-button" aria-label={`Удалить строку ${index + 1}`} disabled={readOnly} onClick={() => onRemove?.(row.id)}><TrashIcon /></button></td>
      </tr>)}</tbody>
    </table>
  </div>;
}
