import type { TradeRow } from '../types/session';
import { normalizeSessionName } from './sessionNames';

// Пустые строки и их технические ID не меняют содержимое сессии.
export function draftFingerprint(name: string, rows: TradeRow[]): string {
  return JSON.stringify({ name: normalizeSessionName(name), trades: rows
    .filter(row => row.isin || row.quantity)
    .map(row => ({ isin: row.isin, quantity: row.quantity })) });
}
