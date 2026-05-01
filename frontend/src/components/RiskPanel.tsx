import { useTradingStore } from '../store/tradingStore'
import axios from 'axios'
import clsx from 'clsx'

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
      <div
        className={clsx('h-full rounded-full transition-all', color)}
        style={{ width: `${Math.min((value / max) * 100, 100)}%` }}
      />
    </div>
  )
}

export default function RiskPanel() {
  const risk = useTradingStore((s) => s.riskMetrics)

  const handleEmergencyStop = async () => {
    if (!confirm('Trigger emergency stop? All positions will be closed immediately.')) return
    await axios.post('/api/bot/emergency-stop')
  }

  const handleResetCB = async () => {
    await axios.post('/api/risk/reset-circuit-breaker')
  }

  if (!risk) return <div className="text-gray-500 text-sm p-4">Loading…</div>

  const pnlColor = risk.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'
  const drawdownColor =
    risk.drawdown_budget_used_pct > 80 ? 'bg-red-500' :
    risk.drawdown_budget_used_pct > 50 ? 'bg-yellow-500' : 'bg-green-500'

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">Risk Monitor</h3>
        {risk.circuit_breaker_triggered && (
          <span className="text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded border border-red-700 animate-pulse">
            CIRCUIT BREAKER
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-gray-500 text-xs">Portfolio</div>
          <div className="font-bold">₹{risk.portfolio_value.toLocaleString('en-IN')}</div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">Daily P&L</div>
          <div className={clsx('font-bold', pnlColor)}>
            {risk.daily_pnl >= 0 ? '+' : ''}₹{Math.abs(risk.daily_pnl).toFixed(0)}
          </div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">Realized</div>
          <div className={clsx('font-semibold text-xs', (risk.realized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
            {(risk.realized_pnl ?? 0) >= 0 ? '+' : ''}₹{Math.abs(risk.realized_pnl ?? 0).toFixed(0)}
          </div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">Unrealized</div>
          <div className={clsx('font-semibold text-xs', (risk.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
            {(risk.unrealized_pnl ?? 0) >= 0 ? '+' : ''}₹{Math.abs(risk.unrealized_pnl ?? 0).toFixed(0)}
          </div>
        </div>
      </div>

      {/* Drawdown bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Daily Drawdown</span>
          <span className={risk.drawdown_budget_used_pct > 80 ? 'text-red-400' : ''}>
            {risk.daily_loss_pct.toFixed(2)}% / {risk.max_daily_drawdown_pct}%
          </span>
        </div>
        <Bar value={risk.drawdown_budget_used_pct} max={100} color={drawdownColor} />
      </div>

      {/* Positions bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Open Positions</span>
          <span>{risk.open_positions} / {risk.max_positions}</span>
        </div>
        <Bar value={risk.open_positions} max={risk.max_positions} color="bg-blue-500" />
      </div>

      {/* Risk multiplier */}
      {risk.risk_multiplier !== 1.0 && (
        <div className="text-xs text-gray-500">
          Risk multiplier: <span className={clsx('font-semibold', risk.risk_multiplier < 1 ? 'text-yellow-400' : 'text-green-400')}>
            {risk.risk_multiplier.toFixed(1)}x
          </span>
          {risk.risk_multiplier < 1 && <span className="ml-1 text-yellow-500">(reduced by day score)</span>}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={handleEmergencyStop}
          className="flex-1 text-xs bg-red-900 hover:bg-red-800 text-red-200 px-3 py-1.5 rounded border border-red-700 transition"
        >
          Emergency Stop
        </button>
        {risk.circuit_breaker_triggered && (
          <button
            onClick={handleResetCB}
            className="flex-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 px-3 py-1.5 rounded border border-gray-600 transition"
          >
            Reset CB
          </button>
        )}
      </div>
    </div>
  )
}
