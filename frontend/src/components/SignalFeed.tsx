import { useTradingStore } from '../store/tradingStore'
import clsx from 'clsx'

function ConfidenceBar({ value }: { value: number }) {
  const pct = (value / 10) * 100
  const color = value >= 7 ? 'bg-green-500' : value >= 5 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="h-1 bg-gray-700 rounded-full w-14">
      <div className={clsx('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
    </div>
  )
}

function SignalBadge({ signal }: { signal: string }) {
  if (signal === 'BUY_CE')
    return <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-green-900 text-green-300">BUY CE</span>
  if (signal === 'BUY_PE')
    return <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-red-900 text-red-300">BUY PE</span>
  return <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">SKIP</span>
}

export default function SignalFeed() {
  const signals = useTradingStore((s) => s.signals)
  const realtimeSignals = useTradingStore((s) => s.realtimeSignals)

  const combined = [...realtimeSignals, ...signals].slice(0, 50)

  if (combined.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center text-gray-500 text-sm">
        No signals yet — bot generates signals during market hours (9:15 AM–3:20 PM IST)
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold text-gray-300">
        AI Signal Feed
      </div>
      <div className="divide-y divide-gray-800/50 max-h-[520px] overflow-y-auto">
        {combined.map((s, i) => (
          <div key={s.id ?? i} className="px-4 py-3 hover:bg-gray-800/20 transition">
            {/* Top row */}
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-white text-sm">{s.symbol ?? s.tradingsymbol}</span>
                <SignalBadge signal={s.signal} />
                {s.executed && (
                  <span className="text-xs bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded">executed</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <ConfidenceBar value={s.confidence ?? 0} />
                <span className="text-xs text-gray-500">{(s.confidence ?? 0).toFixed(1)}/10</span>
              </div>
            </div>

            {/* Option details */}
            {(s.strike || s.expiry) && (
              <div className="flex gap-3 text-xs text-gray-400 mb-1">
                {s.index_name && <span className="text-gray-500">{s.index_name}</span>}
                {s.strike && <span>Strike <span className="text-white">{s.strike}</span></span>}
                {s.expiry && <span>Exp <span className="text-white">{s.expiry}</span></span>}
                {s.lots && <span><span className="text-white">{s.lots}L</span> × {s.lot_size}</span>}
              </div>
            )}

            {/* Premium levels */}
            {(s.entry != null || s.entry_premium != null) && (
              <div className="flex gap-3 text-xs mb-1">
                <span className="text-gray-500">Entry <span className="text-white">₹{(s.entry ?? s.entry_premium)?.toFixed(2)}</span></span>
                <span className="text-gray-500">SL <span className="text-red-400">₹{(s.stop_loss ?? s.stop_premium)?.toFixed(2)}</span></span>
                <span className="text-gray-500">Target <span className="text-green-400">₹{(s.target ?? s.target_premium)?.toFixed(2)}</span></span>
                {s.max_loss && <span className="text-gray-500">MaxLoss <span className="text-orange-400">₹{s.max_loss?.toFixed(0)}</span></span>}
              </div>
            )}

            {/* Reasoning */}
            {s.reasoning && (
              <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">{s.reasoning}</p>
            )}

            <div className="text-xs text-gray-600 mt-1">
              {s.created_at ? new Date(s.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : 'live'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
