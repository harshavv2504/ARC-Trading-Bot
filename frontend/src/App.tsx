import { useWebSocket } from './hooks/useWebSocket'
import { useMarketData } from './hooks/useMarketData'
import { useTradingStore } from './store/tradingStore'
import DayClassifier from './components/DayClassifier'
import RiskPanel from './components/RiskPanel'
import PositionsTable from './components/PositionsTable'
import PnLChart from './components/PnLChart'
import SignalFeed from './components/SignalFeed'
import TradeLog from './components/TradeLog'
import BotControls from './components/BotControls'
import Settings from './components/Settings'
import clsx from 'clsx'

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'positions', label: 'Positions' },
  { id: 'signals',   label: 'Signals'   },
  { id: 'trades',    label: 'Trades'    },
  { id: 'risk',      label: 'Risk'      },
  { id: 'settings',  label: 'Settings'  },
]

export default function App() {
  useWebSocket()
  useMarketData()

  const activeTab = useTradingStore((s) => s.activeTab)
  const setActiveTab = useTradingStore((s) => s.setActiveTab)
  const dc = useTradingStore((s) => s.dayClassification)
  const risk = useTradingStore((s) => s.riskMetrics)

  const ivRank = dc?.iv_rank
  const ivColor = ivRank == null ? 'text-gray-500' :
    ivRank < 20 ? 'text-green-400' : ivRank > 40 ? 'text-red-400' : 'text-yellow-400'

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-8 h-8 bg-green-500 rounded-lg flex items-center justify-center text-black font-black text-sm">
            ARC
          </div>
          <div>
            <div className="text-sm font-bold text-white">ARC Trading Bot</div>
            <div className="text-xs text-gray-500">NSE Index Options · Buy-Side Only</div>
          </div>
        </div>

        {/* Quick stats */}
        <div className="hidden md:flex items-center gap-5 text-xs">
          {dc && (
            <>
              <div>
                <span className="text-gray-500">Day </span>
                <span className={clsx(
                  'font-semibold',
                  dc.classification === 'GOOD' ? 'text-green-400' :
                  dc.classification === 'BAD' ? 'text-red-400' : 'text-yellow-400'
                )}>
                  {dc.score?.toFixed(1) ?? '—'} {dc.classification}
                </span>
              </div>
              <div>
                <span className="text-gray-500">Buy-Side </span>
                <span className={clsx('font-semibold',
                  (dc.buy_side_score ?? 0) >= 7 ? 'text-green-400' :
                  (dc.buy_side_score ?? 0) >= 4 ? 'text-yellow-400' : 'text-red-400'
                )}>
                  {dc.buy_side_score?.toFixed(1) ?? '—'}
                </span>
              </div>
              {ivRank != null && (
                <div>
                  <span className="text-gray-500">IV Rank </span>
                  <span className={clsx('font-semibold', ivColor)}>{ivRank.toFixed(0)}%</span>
                </div>
              )}
              {dc.preferred_side && dc.preferred_side !== 'SKIP' && (
                <div>
                  <span className="text-gray-500">Prefer </span>
                  <span className={clsx('font-semibold',
                    dc.preferred_side === 'CE' ? 'text-green-400' :
                    dc.preferred_side === 'PE' ? 'text-red-400' : 'text-gray-300'
                  )}>
                    {dc.preferred_side}
                  </span>
                </div>
              )}
            </>
          )}
          {risk && (
            <div>
              <span className="text-gray-500">P&L </span>
              <span className={clsx('font-semibold', risk.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                {risk.daily_pnl >= 0 ? '+' : ''}₹{Math.abs(risk.daily_pnl).toFixed(0)}
              </span>
            </div>
          )}
        </div>

        <BotControls />
      </header>

      {/* Tabs */}
      <nav className="border-b border-gray-800 px-6 flex gap-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={clsx(
              'text-xs px-4 py-2.5 border-b-2 transition',
              activeTab === t.id
                ? 'border-green-500 text-green-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 p-6">
        {activeTab === 'dashboard' && (
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 lg:col-span-3 space-y-4">
              <DayClassifier />
              <RiskPanel />
            </div>
            <div className="col-span-12 lg:col-span-9 space-y-4">
              <PnLChart />
              <PositionsTable />
            </div>
          </div>
        )}

        {activeTab === 'positions' && <PositionsTable />}

        {activeTab === 'signals' && (
          <div className="max-w-3xl">
            <SignalFeed />
          </div>
        )}

        {activeTab === 'trades' && (
          <div className="space-y-4">
            <PnLChart />
            <TradeLog />
          </div>
        )}

        {activeTab === 'risk' && (
          <div className="max-w-md space-y-4">
            <RiskPanel />
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 text-xs text-gray-500 space-y-2">
              <div className="font-semibold text-gray-300 mb-2">Risk Rules</div>
              <div>Max risk / trade: <span className="text-white">2%</span> of portfolio</div>
              <div>Max daily drawdown: <span className="text-white">6%</span> — circuit breaker fires</div>
              <div>Max positions: <span className="text-white">5</span> open at once</div>
              <div>Min R:R: <span className="text-white">1:2</span> enforced on every signal</div>
              <div>IV Rank gate: <span className="text-white">skip if IV Rank &gt; 40%</span> (expensive)</div>
              <div>DTE gate: <span className="text-white">no buys within 4 days of expiry</span></div>
              <div>Auto square-off: <span className="text-white">3:20 PM IST</span></div>
              <div>Stop loss: <span className="text-white">50% drop in premium</span></div>
              <div>Target: <span className="text-white">2× entry premium</span></div>
            </div>
          </div>
        )}

        {activeTab === 'settings' && <Settings />}
      </main>
    </div>
  )
}
