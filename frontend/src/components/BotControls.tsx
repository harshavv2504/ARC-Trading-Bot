import { useTradingStore } from '../store/tradingStore'
import axios from 'axios'
import clsx from 'clsx'

export default function BotControls() {
  const risk = useTradingStore((s) => s.riskMetrics)
  const wsConnected = useTradingStore((s) => s.wsConnected)

  const handleStart = () => axios.post('/api/bot/start')
  const handleStop = () => axios.post('/api/bot/stop')
  const handlePreMarket = () => axios.post('/api/bot/run-pre-market')

  const isRunning = risk?.bot_running ?? false

  return (
    <div className="flex items-center gap-3">
      {/* WS Status */}
      <div className="flex items-center gap-1.5 text-xs">
        <div className={clsx('w-2 h-2 rounded-full', wsConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-600')} />
        <span className="text-gray-500">{wsConnected ? 'Live' : 'Disconnected'}</span>
      </div>

      {/* Mode Badge */}
      <span className={clsx(
        'text-xs font-bold px-2 py-0.5 rounded border',
        risk?.bot_running
          ? 'bg-green-950 text-green-300 border-green-700'
          : 'bg-gray-900 text-gray-400 border-gray-700'
      )}>
        {isRunning ? 'RUNNING' : 'STOPPED'}
      </span>

      <button
        onClick={handlePreMarket}
        className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded border border-gray-600 transition"
      >
        Run Day Scan
      </button>

      {isRunning ? (
        <button
          onClick={handleStop}
          className="text-xs bg-yellow-900 hover:bg-yellow-800 text-yellow-200 px-3 py-1.5 rounded border border-yellow-700 transition"
        >
          Stop Bot
        </button>
      ) : (
        <button
          onClick={handleStart}
          className="text-xs bg-green-900 hover:bg-green-800 text-green-200 px-3 py-1.5 rounded border border-green-700 transition"
        >
          Start Bot
        </button>
      )}
    </div>
  )
}
