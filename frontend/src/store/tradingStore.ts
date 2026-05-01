import { create } from 'zustand'

export interface Position {
  id: number
  symbol: string
  mode: string
  side: 'BUY'
  entry_price: number      // entry premium
  current_price: number    // current premium
  quantity: number
  unrealized_pnl: number
  stop_loss: number | null
  target: number | null
  opened_at: string
  exchange: string
  product: string
}

export interface Signal {
  id: number
  symbol: string
  index_name: string | null
  signal: 'BUY_CE' | 'BUY_PE' | 'SKIP'
  option_type: 'CE' | 'PE' | null
  strike: number | null
  expiry: string | null
  lots: number | null
  lot_size: number | null
  confidence: number
  entry: number | null       // entry premium
  target: number | null      // target premium
  stop_loss: number | null   // stop premium
  max_loss: number | null
  reasoning: string | null
  executed: boolean
  created_at: string
}

export interface Trade {
  id: number
  symbol: string
  mode: string
  side: 'BUY'
  entry_price: number   // entry premium
  exit_price: number | null
  quantity: number
  pnl: number | null
  entry_time: string
  exit_time: string | null
  status: string
  stop_loss: number | null
  target: number | null
  notes: string | null
}

export interface DayClassification {
  classification: 'GOOD' | 'NEUTRAL' | 'BAD' | 'PENDING'
  score: number | null
  buy_side_score: number | null
  vix: number | null
  iv_rank: number | null
  premium_env: string | null
  fii_net: number | null
  ml_direction: string | null
  ml_regime: string | null
  preferred_side: 'CE' | 'PE' | 'EITHER' | 'SKIP' | null
  key_reasons: string[]
}

export interface RiskMetrics {
  portfolio_value: number
  daily_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  daily_loss_pct: number
  max_daily_drawdown_pct: number
  drawdown_budget_used_pct: number
  open_positions: number
  max_positions: number
  circuit_breaker_triggered: boolean
  risk_multiplier: number
  bot_running: boolean
}

export interface PnlSnapshot {
  date: string
  realized_pnl: number
  total_trades: number
  win_rate: number
  portfolio_value: number
}

interface TradingStore {
  activeTab: string
  tradingMode: string
  positions: Position[]
  signals: Signal[]
  trades: Trade[]
  pnlHistory: PnlSnapshot[]
  dayClassification: DayClassification | null
  riskMetrics: RiskMetrics | null
  realtimeSignals: any[]
  wsConnected: boolean

  setActiveTab: (tab: string) => void
  setPositions: (p: Position[]) => void
  setSignals: (s: Signal[]) => void
  setTrades: (t: Trade[]) => void
  setPnlHistory: (h: PnlSnapshot[]) => void
  setDayClassification: (d: DayClassification) => void
  setRiskMetrics: (r: RiskMetrics) => void
  addRealtimeSignal: (s: any) => void
  setWsConnected: (c: boolean) => void
  setTradingMode: (m: string) => void
}

export const useTradingStore = create<TradingStore>((set) => ({
  activeTab: 'dashboard',
  tradingMode: 'paper',
  positions: [],
  signals: [],
  trades: [],
  pnlHistory: [],
  dayClassification: null,
  riskMetrics: null,
  realtimeSignals: [],
  wsConnected: false,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setPositions: (positions) => set({ positions }),
  setSignals: (signals) => set({ signals }),
  setTrades: (trades) => set({ trades }),
  setPnlHistory: (pnlHistory) => set({ pnlHistory }),
  setDayClassification: (dayClassification) => set({ dayClassification }),
  setRiskMetrics: (riskMetrics) => set({ riskMetrics }),
  addRealtimeSignal: (s) =>
    set((state) => ({ realtimeSignals: [s, ...state.realtimeSignals].slice(0, 100) })),
  setWsConnected: (wsConnected) => set({ wsConnected }),
  setTradingMode: (tradingMode) => set({ tradingMode }),
}))
