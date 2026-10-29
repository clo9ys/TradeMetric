import { useState } from 'react';
import { SessionPanel } from '../../components/session-panel/SessionPanel';
import { createEmptyTrade, createEmptyTrades } from '../../types/session';

export function NewSessionPage() {
  const [rows, setRows] = useState(createEmptyTrades);
  const [message, setMessage] = useState('');

  function updateRow(id: string, field: 'isin' | 'quantity', value: string) {
    setRows(previous => previous.map(row => row.id === id ? { ...row, [field]: value } : row));
    setMessage('');
  }

  function calculate() {
    const enteredRows = rows.filter(row => row.isin || row.quantity);
    if (enteredRows.length === 0) {
      setMessage('Введите ISIN и объём хотя бы одной сделки.');
      return;
    }
    if (enteredRows.some(row => !/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(row.isin) || Number(row.quantity) <= 0)) {
      setMessage('Для каждой сделки укажите ISIN из 12 символов и положительный целый объём.');
      return;
    }
    setMessage('Расчёт станет доступен после подключения сервера.');
  }

  return <section aria-label="Новая сессия"><SessionPanel rows={rows} onChange={updateRow} onAdd={() => { setRows(previous => [...previous, createEmptyTrade()]); setMessage(''); }} onRemove={id => { setRows(previous => previous.filter(row => row.id !== id)); setMessage(''); }} onCalculate={calculate} message={message} /></section>;
}
