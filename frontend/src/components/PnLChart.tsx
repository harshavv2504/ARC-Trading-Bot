import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import axios from 'axios'

interface PnlPoint {
  date: string
  realized_pnl: number
  portfolio_value: number
  win_rate: number
}

export default function PnLChart() {
  const [data, setData] = useState<PnlPoint[]>([])

  useEffect(() => {
    axios.get('/api/trades/pnl').then((r) => setData(r.data)).catch(() => {})
  }, [])

  if (data.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center text-gray-500 text-sm h-48 flex items-center justify-center">
        No P&L history yet
      </div>
    )
  }

  const maxAbs = Math.max(...data.map((d) => Math.abs(d.realized_pnl)), 1)

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className="text-sm font-semibold text-gray-300 mb-4">Equity Curve (Realized P&L)</div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
          <YAxis
            tick={{ fontSize: 10, fill: '#6b7280' }}
            tickFormatter={(v) => `₹${v >= 0 ? '+' : ''}${v}`}
            domain={[-maxAbs * 1.1, maxAbs * 1.1]}
          />
          <Tooltip
            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(v: number) => [`₹${v >= 0 ? '+' : ''}${v.toFixed(0)}`, 'P&L']}
          />
          <Area
            type="monotone"
            dataKey="realized_pnl"
            stroke="#22c55e"
            fill="url(#pnlGrad)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
