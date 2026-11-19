import { apiRequest } from './client';
import type { CalculationResult, TradeRow } from '../types/session';

export async function calculateTrades(lastTradingDate: string, rows: TradeRow[]): Promise<CalculationResult> {
  const saved = await apiRequest<{ id: string }>('/api/calculations', {
    method: 'POST',
    body: {
      last_trading_date: lastTradingDate,
      trades: rows.map(row => ({ client_trade_id: row.id, isin: row.isin, quantity: Number(row.quantity) })),
    },
  });
  return apiRequest<CalculationResult>(`/api/calculations/${saved.id}`);
}
