export type Page = 'login' | 'new' | 'history';
export type Currency = 'RUB' | 'USD' | 'EUR';

export interface TradeRow {
  id: string;
  isin: string;
  quantity: string;
}

export interface DemoInstrument {
  isin: string;
  issue_name: string;
  issuer_name: string;
  currency: string;
  coupon_type: 'fixed' | 'floating';
  default_quantity: number;
}

export interface DemoCalculationResult {
  calculation_id: string;
  calculated_at?: string;
  source: 'demo';
  currency: 'RUB';
  total_dv01_rub: string;
  total_fair_value_rub: string;
  trades: { isin: string; issue_name?: string; issuer_name?: string; currency?: string; coupon_type?: 'fixed' | 'floating'; quantity: number; fair_value_rub: string; dv01_rub: string }[];
}

export interface TradeRowError {
  isin?: string;
  quantity?: string;
}

export function createEmptyTrade(): TradeRow {
  return { id: crypto.randomUUID(), isin: '', quantity: '' };
}

export function createEmptyTrades(): TradeRow[] {
  return Array.from({ length: 5 }, createEmptyTrade);
}
