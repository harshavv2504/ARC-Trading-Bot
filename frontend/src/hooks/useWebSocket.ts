import { useEffect, useRef } from 'react'
import { useTradingStore } from '../store/tradingStore'

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { setWsConnected, setRiskMetrics, setDayClassification, setPositions, addRealtimeSignal } =
    useTradingStore()

  const connect = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws.current = new WebSocket(`${protocol}://${window.location.host}/ws`)

    ws.current.onopen = () => {
      setWsConnected(true)
      const ping = setInterval(() => {
        if (ws.current?.readyState === WebSocket.OPEN) ws.current.send('ping')
        else clearInterval(ping)
      }, 20000)
    }

    ws.current.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        switch (msg.event) {
          case 'risk_update':
            setRiskMetrics(msg)
            break
          case 'day_classification':
            setDayClassification({
              classification: msg.classification ?? 'PENDING',
              score:          msg.score,
              buy_side_score: msg.buy_side_score,
              vix:            msg.vix,
              iv_rank:        msg.iv_rank,
              premium_env:    msg.premium_env,
              fii_net:        msg.fii_net,
              ml_direction:   msg.ml_direction,
              ml_regime:      msg.ml_regime ?? null,
              preferred_side: msg.trade_side ?? null,
              key_reasons:    msg.key_reasons ?? [],
            })
            break
          case 'signal':
            // BUY_CE / BUY_PE signals
            if (msg.signal === 'BUY_CE' || msg.signal === 'BUY_PE') {
              addRealtimeSignal({
                ...msg,
                symbol:     msg.tradingsymbol ?? msg.index,
                index_name: msg.index,
                entry:      msg.entry,
                created_at: new Date().toISOString(),
              })
            }
            break
          case 'positions_update':
            if (msg.positions) setPositions(msg.positions)
            break
          case 'emergency_stop':
            addRealtimeSignal({ signal: 'EMERGENCY_STOP', reasoning: msg.reason, created_at: new Date().toISOString() })
            break
          default:
            break
        }
      } catch {}
    }

    ws.current.onclose = () => {
      setWsConnected(false)
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.current.onerror = () => ws.current?.close()
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [])
}
