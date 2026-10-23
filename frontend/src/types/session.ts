export type Page = 'login' | 'new' | 'history';
export type Currency = 'RUB' | 'USD' | 'EUR';

export interface TradeRow {
  id: string;
  isin: string;
  quantity: string;
}

export function createEmptyTrade(): TradeRow {
  return { id: crypto.randomUUID(), isin: '', quantity: '' };
}

export function createEmptyTrades(): TradeRow[] {
  return Array.from({ length: 5 }, createEmptyTrade);
}
