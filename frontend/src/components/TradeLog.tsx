import { useTradingStore } from '../store/tradingStore'
import clsx from 'clsx'

function parseNotes(notes: string | null) {
  if (!notes) return {}
  const out: Record<string, string> = {}
  for (const part of notes.split(' ')) {
    const [k, v] = part.split('=')
    if (k && v) out[k] = v
  }
  return out
}

export default function TradeLog() {
  const trades = useTradingStore((s) => s.trades)

  if (trades.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center text-gray-500 text-sm">
        No trades yet
      </div>
    )
  }

  const closed = trades.filter((t) => t.status === 'closed')
  const totalPnl = closed.reduce((sum, t) => sum + (t.pnl ?? 0), 0)
  const wins = closed.filter((t) => (t.pnl ?? 0) > 0).length
  const winRate = closed.length ? ((wins / closed.length) * 100).toFixed(0) : '0'

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-300">
          Trade History ({trades.length})
        </span>
        <div className="flex gap-4 text-xs">
          <span className="text-gray-500">
            Win Rate: <span className="text-white">{winRate}%</span>
          </span>
          <span className={clsx('font-semibold', totalPnl >= 0 ? 'text-green-400' : 'text-red-400')}>
            Realized: {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toFixed(0)}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left px-4 py-2">Option</th>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-right px-4 py-2">Qty</th>
              <th className="text-right px-4 py-2">Entry ₹</th>
              <th className="text-right px-4 py-2">Exit ₹</th>
              <th className="text-right px-4 py-2">P&L ₹</th>
              <th className="text-left px-4 py-2">Exit Reason</th>
              <th className="text-left px-4 py-2">Time</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const pnlColor = (t.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
              const notes = parseNotes(t.notes)
              const exitReason = notes.reason ?? (t.status === 'open' ? 'open' : t.status)

              return (
                <tr key={t.id} className="border-b border-gray-800/30 hover:bg-gray-800/20">
                  <td className="px-4 py-2">
                    <div className="font-semibold text-white">{t.symbol}</div>
                    {notes.strike && (
                      <div className="text-gray-600">
                        {notes.index} {notes.strike} {notes.type} {notes.expiry}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {notes.type ? (
                      <span className={clsx(
                        'px-1.5 py-0.5 rounded font-bold',
                        notes.type === 'CE' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                      )}>
                        {notes.type}
                      </span>
                    ) : (
                      <span className="text-gray-500">BUY</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">{t.quantity}</td>
                  <td className="px-4 py-2 text-right">{t.entry_price?.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right">
                    {t.exit_price != null ? t.exit_price.toFixed(2) : '—'}
                  </td>
                  <td className={clsx('px-4 py-2 text-right font-semibold', pnlColor)}>
                    {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}₹${t.pnl.toFixed(0)}` : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <span className={clsx('text-xs',
                      exitReason === 'target_hit' ? 'text-green-400' :
                      exitReason === 'stop_loss' ? 'text-red-400' :
                      exitReason === 'eod_squareoff' ? 'text-yellow-400' :
                      exitReason === 'open' ? 'text-blue-400' : 'text-gray-500'
                    )}>
                      {exitReason}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {t.entry_time
                      ? new Date(t.entry_time).toLocaleString('en-IN', { timeStyle: 'short', dateStyle: 'short' })
                      : ''}
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
