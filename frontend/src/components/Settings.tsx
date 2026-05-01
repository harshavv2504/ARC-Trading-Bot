import { useState } from 'react'
import { useTradingStore } from '../store/tradingStore'
import axios from 'axios'

interface Field {
  key: string
  label: string
  type: 'text' | 'number'
  hint: string
  group: string
}

const FIELDS: Field[] = [
  // Risk
  { key: 'trading_mode',       label: 'Trading Mode',           type: 'text',   hint: 'paper | live',  group: 'Risk' },
  { key: 'max_risk_per_trade', label: 'Max Risk / Trade (%)',   type: 'number', hint: '2.0',            group: 'Risk' },
  { key: 'max_daily_drawdown', label: 'Max Daily Drawdown (%)', type: 'number', hint: '6.0',            group: 'Risk' },
  { key: 'max_positions',      label: 'Max Open Positions',     type: 'number', hint: '5',              group: 'Risk' },
  { key: 'min_rr_ratio',       label: 'Min Risk:Reward',        type: 'number', hint: '2.0',            group: 'Risk' },
  { key: 'squareoff_time',     label: 'Auto Square-off (IST)',  type: 'text',   hint: '15:20',          group: 'Risk' },
  // Options
  { key: 'max_iv_rank',        label: 'Max IV Rank (%)',        type: 'number', hint: '40 — skip above this', group: 'Options' },
  { key: 'min_dte',            label: 'Min Days to Expiry',     type: 'number', hint: '4',              group: 'Options' },
  { key: 'option_stop_loss_pct', label: 'Option SL (% of premium)', type: 'number', hint: '50',        group: 'Options' },
]

const GROUPS = ['Risk', 'Options']

export default function Settings() {
  const risk = useTradingStore((s) => s.riskMetrics)
  const [values, setValues] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState<string | null>(null)
  const [loginUrl, setLoginUrl] = useState('')
  const [kiteToken, setKiteToken] = useState('')
  const [kiteMsg, setKiteMsg] = useState('')

  const handleSave = async (key: string) => {
    const value = values[key]
    if (!value) return
    await axios.post('/api/settings', { key, value })
    setSaved(key)
    setTimeout(() => setSaved(null), 2000)
  }

  const handleGetLoginUrl = async () => {
    const r = await axios.post('/api/bot/kite-login')
    setLoginUrl(r.data.login_url)
  }

  const handleGenerateSession = async () => {
    const r = await axios.post(`/api/bot/kite-session?request_token=${kiteToken}`)
    setKiteMsg(r.data.status === 'authenticated' ? 'Authenticated!' : r.data.message)
  }

  const handleTrainModels = async () => {
    await axios.post('/api/bot/train-models')
    alert('ML training started — watch logs (~15 min). Models activate automatically when done.')
  }

  const grouped = GROUPS.reduce((acc, g) => {
    acc[g] = FIELDS.filter((f) => f.group === g)
    return acc
  }, {} as Record<string, Field[]>)

  return (
    <div className="space-y-6 max-w-2xl">
      {GROUPS.map((group) => (
        <div key={group} className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">{group} Settings</h3>
          <div className="space-y-3">
            {grouped[group].map((f) => (
              <div key={f.key} className="flex items-center gap-3">
                <label className="text-xs text-gray-400 w-52 shrink-0">{f.label}</label>
                <input
                  type={f.type}
                  placeholder={f.hint}
                  value={values[f.key] ?? ''}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-green-600"
                />
                <button
                  onClick={() => handleSave(f.key)}
                  className="text-xs bg-green-900 hover:bg-green-800 text-green-200 px-3 py-1.5 rounded border border-green-700 transition w-16"
                >
                  {saved === f.key ? 'Saved!' : 'Save'}
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Kite Auth */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-1">Kite Connect Auth</h3>
        <p className="text-xs text-gray-500 mb-4">Required for live market data and order placement.</p>
        <div className="space-y-3">
          <button
            onClick={handleGetLoginUrl}
            className="text-xs bg-blue-900 hover:bg-blue-800 text-blue-200 px-4 py-2 rounded border border-blue-700 transition"
          >
            Get Login URL
          </button>
          {loginUrl && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500">Login, then copy the <code className="text-gray-300">request_token</code> from the redirect URL:</p>
              <a href={loginUrl} target="_blank" rel="noreferrer" className="text-xs text-blue-400 underline break-all">
                {loginUrl}
              </a>
            </div>
          )}
          <div className="flex items-center gap-3">
            <input
              type="text"
              placeholder="Paste request_token"
              value={kiteToken}
              onChange={(e) => setKiteToken(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-green-600"
            />
            <button
              onClick={handleGenerateSession}
              className="text-xs bg-green-900 hover:bg-green-800 text-green-200 px-3 py-1.5 rounded border border-green-700 transition"
            >
              Authenticate
            </button>
          </div>
          {kiteMsg && <p className="text-xs text-green-400">{kiteMsg}</p>}
        </div>
      </div>

      {/* ML Models */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-1">ML Models</h3>
        <p className="text-xs text-gray-500 mb-4">
          Train XGBoost direction + RandomForest regime + GradientBoosting timing models on NIFTY/BANKNIFTY data from 2020. Takes ~15 min.
        </p>
        <button
          onClick={handleTrainModels}
          className="text-xs bg-purple-900 hover:bg-purple-800 text-purple-200 px-4 py-2 rounded border border-purple-700 transition"
        >
          Train ML Models
        </button>
        <p className="text-xs text-gray-600 mt-2">
          Or run from terminal: <code className="text-gray-400">venv/bin/python -m backend.ml.train</code>
        </p>
      </div>

      {/* Info */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 text-xs text-gray-500 space-y-1">
        <div>Portfolio: <span className="text-white">₹{risk?.portfolio_value?.toLocaleString('en-IN') ?? '—'}</span></div>
        <div>Strategy: Index options buy-side (NIFTY / BANKNIFTY CE+PE buying only)</div>
        <div>IV Rank gate: skip buying when IV Rank &gt; 40% (expensive premium)</div>
        <div>Set API keys in <code className="text-gray-400">.env</code> — KITE_API_KEY, OPENAI_API_KEY / ANTHROPIC_API_KEY</div>
      </div>
    </div>
  )
}
