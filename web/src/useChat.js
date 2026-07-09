import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * WebSocket-backed conversation state. The server pushes a snapshot on
 * connect, then incremental events; message_chunk carries the full content
 * so far, so updates are simple index-based patches.
 */
export function useChat() {
  const [connected, setConnected] = useState(false)
  const [running, setRunning] = useState(false)
  const [paused, setPaused] = useState(false)
  const [messages, setMessages] = useState([])
  const [status, setStatus] = useState('Ready')
  const [turn, setTurn] = useState({ current: 0, max: 20 })
  const [usage, setUsage] = useState({ total_tokens: 0, estimated_cost: 0 })
  const [typing, setTyping] = useState(null)
  const [topic, setTopic] = useState('')
  const [toasts, setToasts] = useState([])
  const wsRef = useRef(null)
  const toastId = useRef(0)

  const toast = useCallback((text, kind = 'info') => {
    const id = ++toastId.current
    setToasts((t) => [...t, { id, text, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500)
  }, [])

  useEffect(() => {
    let closed = false

    function connect() {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) setTimeout(connect, 1500) // auto-reconnect
      }
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data)
        switch (ev.type) {
          case 'snapshot':
            setRunning(ev.running)
            setPaused(ev.paused)
            setTopic(ev.topic || '')
            setTurn(ev.turn)
            setMessages(ev.messages.map((m) => ({ ...m, streaming: false })))
            setUsage({
              total_tokens: ev.usage.total_tokens || 0,
              estimated_cost: ev.usage.estimated_cost || 0,
            })
            break
          case 'status':
            setStatus(ev.text)
            if (ev.text === 'Conversation starting...') { setRunning(true); setPaused(false) }
            if (ev.text === 'Paused') setPaused(true)
            if (ev.text === 'Resumed') setPaused(false)
            break
          case 'turn':
            setTurn({ current: ev.current, max: ev.max })
            break
          case 'typing':
            setTyping({ persona: ev.persona, index: ev.index })
            break
          case 'typing_end':
            setTyping(null)
            break
          case 'message_start':
            setMessages((msgs) => {
              const next = [...msgs]
              next[ev.index] = {
                persona: ev.persona, role: ev.role,
                color_index: ev.color_index, content: '', streaming: true,
              }
              return next
            })
            break
          case 'message_chunk':
            setMessages((msgs) => {
              const next = [...msgs]
              if (next[ev.index]) next[ev.index] = { ...next[ev.index], content: ev.content }
              return next
            })
            break
          case 'message_complete':
            setMessages((msgs) => {
              const next = [...msgs]
              next[ev.index] = {
                persona: ev.persona, role: ev.role, content: ev.content,
                color_index: ev.color_index, streaming: false,
              }
              return next
            })
            break
          case 'usage':
            setUsage({ total_tokens: ev.tokens, estimated_cost: ev.cost })
            break
          case 'error':
            toast(ev.text, 'danger')
            break
          case 'done':
            setRunning(false)
            setPaused(false)
            setTyping(null)
            setStatus(ev.reason === 'max_turns'
              ? `Finished — ${ev.turns} turns completed`
              : 'Conversation stopped')
            break
          default:
            break
        }
      }
    }

    connect()
    return () => { closed = true; wsRef.current?.close() }
  }, [toast])

  const resetLocal = useCallback((newTopic, maxTurns) => {
    setMessages([])
    setTopic(newTopic)
    setTurn({ current: 0, max: maxTurns })
    setUsage({ total_tokens: 0, estimated_cost: 0 })
  }, [])

  return {
    connected, running, paused, messages, status, turn, usage,
    typing, topic, toasts, toast, resetLocal, setRunning, setPaused,
  }
}
