import { useEffect } from 'react'
import axios from 'axios'
import { useTradingStore } from '../store/tradingStore'

export function useMarketData() {
  const { setPositions, setSignals, setTrades, setPnlHistory, setDayClassification, setRiskMetrics } =
    useTradingStore()

  const fetchAll = async () => {
    try {
      const [dashboard, signals, trades, pnl] = await Promise.all([
        axios.get('/api/dashboard'),
        axios.get('/api/signals?limit=50'),
        axios.get('/api/trades?limit=100'),
        axios.get('/api/trades/pnl'),
      ])

      const d = dashboard.data
      setPositions(d.positions || [])
      setRiskMetrics(d.risk)
      if (d.day_classification) setDayClassification(d.day_classification)
      setSignals(signals.data || [])
      setTrades(trades.data || [])
      setPnlHistory(pnl.data || [])
    } catch (e) {
      console.error('Data fetch error:', e)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [])
}
