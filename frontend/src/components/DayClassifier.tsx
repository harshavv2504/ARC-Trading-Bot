import { useTradingStore } from '../store/tradingStore'
import clsx from 'clsx'

const CLS_COLOR = {
  GOOD:    'text-green-400 border-green-600 bg-green-950/60',
  NEUTRAL: 'text-yellow-400 border-yellow-600 bg-yellow-950/60',
  BAD:     'text-red-400 border-red-600 bg-red-950/60',
  PENDING: 'text-gray-400 border-gray-700 bg-gray-900',
}

const DIR_COLOR: Record<string, string> = {
  STRONG_UP:   'text-green-300',
  UP:          'text-green-400',
  FLAT:        'text-gray-400',
  DOWN:        'text-red-400',
  STRONG_DOWN: 'text-red-300',
}

const DIR_LABEL: Record<string, string> = {
  STRONG_UP: '↑↑ Strong Bull', UP: '↑ Bull',
  FLAT: '→ Flat', DOWN: '↓ Bear', STRONG_DOWN: '↓↓ Strong Bear',
}

const PREM_COLOR: Record<string, string> = {
  CHEAP:     'text-green-400',
  FAIR:      'text-yellow-400',
  EXPENSIVE: 'text-red-400',
}

function ScoreBar({ value, max = 10, color }: { value: number; max?: number; color: string }) {
  return (
    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
      <div
        className={clsx('h-full rounded-full transition-all', color)}
        style={{ width: `${Math.min((value / max) * 100, 100)}%` }}
      />
    </div>
  )
}

export default function DayClassifier() {
  const dc = useTradingStore((s) => s.dayClassification)
  const cls = dc?.classification ?? 'PENDING'

  return (
    <div className={clsx('rounded-xl border p-4 space-y-3', CLS_COLOR[cls])}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400 uppercase tracking-widest">Today's Market</span>
        <span className={clsx('text-xs font-bold px-2 py-0.5 rounded border', CLS_COLOR[cls])}>
          {cls}
        </span>
      </div>

      {/* Scores */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-gray-500 mb-1">Day Score</div>
          <div className="text-3xl font-bold">{dc?.score?.toFixed(1) ?? '—'}</div>
          <ScoreBar value={dc?.score ?? 0} color="bg-blue-500" />
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Buy-Side Score</div>
          <div className={clsx('text-3xl font-bold',
            (dc?.buy_side_score ?? 0) >= 7 ? 'text-green-400' :
            (dc?.buy_side_score ?? 0) >= 4 ? 'text-yellow-400' : 'text-red-400'
          )}>
            {dc?.buy_side_score?.toFixed(1) ?? '—'}
          </div>
          <ScoreBar
            value={dc?.buy_side_score ?? 0}
            color={(dc?.buy_side_score ?? 0) >= 7 ? 'bg-green-500' : (dc?.buy_side_score ?? 0) >= 4 ? 'bg-yellow-500' : 'bg-red-500'}
          />
        </div>
      </div>

      {/* Preferred side */}
      {dc?.preferred_side && dc.preferred_side !== 'SKIP' && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Prefer:</span>
          <span className={clsx(
            'text-xs font-bold px-2 py-0.5 rounded',
            dc.preferred_side === 'CE' ? 'bg-green-900 text-green-300' :
            dc.preferred_side === 'PE' ? 'bg-red-900 text-red-300' :
            'bg-gray-800 text-gray-300'
          )}>
            {dc.preferred_side === 'CE' ? 'BUY CE (Calls)' :
             dc.preferred_side === 'PE' ? 'BUY PE (Puts)' : 'Either'}
          </span>
        </div>
      )}
      {dc?.preferred_side === 'SKIP' && (
        <div className="text-xs text-red-400 font-semibold">⚠ SKIP — avoid buying options today</div>
      )}

      {/* Indicators */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        {dc?.vix != null && (
          <div className="flex justify-between">
            <span className="text-gray-500">VIX</span>
            <span className="font-semibold">{dc.vix.toFixed(2)}</span>
          </div>
        )}
        {dc?.iv_rank != null && (
          <div className="flex justify-between">
            <span className="text-gray-500">IV Rank</span>
            <span className={clsx('font-semibold',
              dc.iv_rank < 20 ? 'text-green-400' : dc.iv_rank > 40 ? 'text-red-400' : 'text-yellow-400'
            )}>
              {dc.iv_rank.toFixed(0)}%
            </span>
          </div>
        )}
        {dc?.fii_net != null && (
          <div className="flex justify-between">
            <span className="text-gray-500">FII</span>
            <span className={clsx('font-semibold', (dc.fii_net ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
              {(dc.fii_net ?? 0) >= 0 ? '+' : ''}{((dc.fii_net ?? 0) / 100).toFixed(0)}Cr
            </span>
          </div>
        )}
        {dc?.premium_env && (
          <div className="flex justify-between">
            <span className="text-gray-500">Premium</span>
            <span className={clsx('font-semibold', PREM_COLOR[dc.premium_env] ?? 'text-gray-300')}>
              {dc.premium_env}
            </span>
          </div>
        )}
      </div>

      {/* ML Direction */}
      {dc?.ml_direction && (
        <div className="pt-1 border-t border-gray-800/60">
          <span className="text-xs text-gray-500">ML Direction: </span>
          <span className={clsx('text-xs font-semibold', DIR_COLOR[dc.ml_direction] ?? 'text-gray-300')}>
            {DIR_LABEL[dc.ml_direction] ?? dc.ml_direction}
          </span>
        </div>
      )}

      {/* Key Reasons */}
      {(dc?.key_reasons?.length ?? 0) > 0 && (
        <ul className="space-y-1 pt-1 border-t border-gray-800/60">
          {(dc?.key_reasons ?? []).slice(0, 3).map((r, i) => (
            <li key={i} className="text-xs text-gray-300 flex gap-1">
              <span className="text-gray-600 shrink-0">•</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
