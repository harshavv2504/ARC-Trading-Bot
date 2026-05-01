import { useTradingStore } from '../store/tradingStore'
import clsx from 'clsx'

function PremiumBar({ current, entry, stop, target }: {
  current: number; entry: number; stop: number | null; target: number | null
}) {
  if (!stop || !target) return null
  const range = target - stop
  const pos = ((current - stop) / range) * 100
  const clamped = Math.max(0, Math.min(100, pos))
  return (
    <div className="relative h-1 bg-gray-700 rounded-full w-16 mt-0.5">
      <div className="absolute h-full bg-red-800 rounded-l-full" style={{ width: '33%' }} />
      <div className="absolute h-full bg-green-800 rounded-r-full right-0" style={{ width: '33%' }} />
      <div
        className="absolute w-1.5 h-1.5 bg-white rounded-full -top-0.5 -translate-x-0.5"
        style={{ left: `${clamped}%` }}
      />
    </div>
  )
}

export default function PositionsTable() {
  const positions = useTradingStore((s) => s.positions)

  if (positions.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center text-gray-500 text-sm">
        No open positions — signals will auto-execute during market hours
      </div>
    )
  }

  const totalPnl = positions.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0)

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-300">
          Open Positions ({positions.length})
        </span>
        <span className={clsx('text-sm font-bold', totalPnl >= 0 ? 'text-green-400' : 'text-red-400')}>
          {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toFixed(0)} unrealized
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left px-4 py-2">Option</th>
              <th className="text-right px-4 py-2">Qty</th>
              <th className="text-right px-4 py-2">Entry ₹</th>
              <th className="text-right px-4 py-2">LTP ₹</th>
              <th className="text-right px-4 py-2">Chg%</th>
              <th className="text-right px-4 py-2">P&L ₹</th>
              <th className="text-right px-4 py-2">SL ₹</th>
              <th className="text-right px-4 py-2">Target ₹</th>
              <th className="text-center px-4 py-2">Range</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const pnlColor = (p.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
              const chgPct = p.entry_price
                ? ((p.current_price - p.entry_price) / p.entry_price) * 100
                : 0

              return (
                <tr key={p.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition">
                  <td className="px-4 py-2">
                    <div className="font-semibold text-white leading-tight">{p.symbol}</div>
                    <div className="text-gray-600 text-xs">{p.exchange} · {p.product}</div>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">{p.quantity}</td>
                  <td className="px-4 py-2 text-right">{p.entry_price?.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right font-semibold text-white">
                    {p.current_price?.toFixed(2)}
                  </td>
                  <td className={clsx('px-4 py-2 text-right', chgPct >= 0 ? 'text-green-400' : 'text-red-400')}>
                    {chgPct >= 0 ? '+' : ''}{chgPct.toFixed(1)}%
                  </td>
                  <td className={clsx('px-4 py-2 text-right font-semibold', pnlColor)}>
                    {(p.unrealized_pnl ?? 0) >= 0 ? '+' : ''}₹{(p.unrealized_pnl ?? 0).toFixed(0)}
                  </td>
                  <td className="px-4 py-2 text-right text-red-400">
                    {p.stop_loss ? p.stop_loss.toFixed(2) : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-green-400">
                    {p.target ? p.target.toFixed(2) : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex justify-center">
                      <PremiumBar
                        current={p.current_price}
                        entry={p.entry_price}
                        stop={p.stop_loss}
                        target={p.target}
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
